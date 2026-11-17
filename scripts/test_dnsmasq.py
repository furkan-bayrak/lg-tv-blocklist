#!/usr/bin/env python3
"""Offline resolver integration: python3 scripts/test_dnsmasq.py.

Requires dnsmasq and dig on PATH. All configuration, generated lists and logs
stay in a temporary directory; DNS traffic stays on IPv4 loopback high ports.
The A/AAAA answer tests do not establish TV routing or feature compatibility.
"""

import io
import ipaddress
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

LOOPBACK = "127.0.0.1"
STARTUP_TIMEOUT = 8
COMMAND_TIMEOUT = 5
QUERY_TIMEOUT = 3
STOP_TIMEOUT = 3


class TestDnsmasqIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dnsmasq = shutil.which("dnsmasq")
        cls.dig = shutil.which("dig")
        missing = [name for name in ("dnsmasq", "dig") if not getattr(cls, name)]
        if missing:
            raise RuntimeError(
                "dnsmasq integration prerequisites missing from PATH: "
                + ", ".join(missing)
                + ". Install dnsmasq and dig (Ubuntu: dnsmasq-base and dnsutils); "
                "this integration test must run, not skip."
            )

    def logs(self):
        return "\n".join(
            f"--- {path.name} ---\n{path.read_text(encoding='utf-8', errors='replace')}"
            for path in self.log_paths
        )

    def unused_port(self):
        # DNS needs both transports. Reserve both while selecting a port, then
        # release them immediately before starting the test-owned resolver.
        for _ in range(20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp, \
                 socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                tcp.bind((LOOPBACK, 0))
                port = tcp.getsockname()[1]
                if port <= 1023:
                    continue
                try:
                    udp.bind((LOOPBACK, port))
                except OSError:
                    continue
                return port
        self.fail("Could not allocate an unprivileged loopback TCP/UDP port")

    @contextmanager
    def resolver(self, root, name, extra_config):
        port = self.unused_port()
        config = root / f"{name}.conf"
        config.write_text(
            "\n".join([
                f"port={port}",
                f"listen-address={LOOPBACK}",
                "bind-interfaces",
                "no-hosts",
                "no-resolv",
                "cache-size=0",
                "log-facility=-",
                "log-queries",
                extra_config,
                "",
            ]),
            encoding="utf-8",
            newline="\n",
        )
        # An explicit conf-file replaces /etc/dnsmasq.conf. Included generated
        # snippets are syntax-checked too, before any resolver is started.
        checked = subprocess.run(
            [self.dnsmasq, "--test", f"--conf-file={config}"],
            capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
        )
        self.assertEqual(
            checked.returncode, 0,
            f"dnsmasq --test failed for {config.name}:\n"
            f"{checked.stdout}{checked.stderr}\n{self.logs()}",
        )
        log_path = root / f"{name}.log"
        self.log_paths.append(log_path)
        with log_path.open("w", encoding="utf-8") as log:
            process = None
            try:
                # Debug mode neither forks nor changes UID nor writes a PID
                # file. Only this Popen child is ever signalled during cleanup.
                process = subprocess.Popen(
                    [self.dnsmasq, "--no-daemon", f"--conf-file={config}"],
                    stdout=log, stderr=subprocess.STDOUT,
                )
                deadline = time.monotonic() + STARTUP_TIMEOUT
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail(f"{name} exited during startup: {process.returncode}")
                    try:
                        with socket.create_connection((LOOPBACK, port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    self.fail(f"{name} did not start within {STARTUP_TIMEOUT}s")
                yield port
                self.assertIsNone(process.poll(), f"{name} exited unexpectedly")
            except Exception as error:
                raise AssertionError(f"{error}\n{self.logs()}") from error
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=STOP_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=STOP_TIMEOUT)

    def assert_answer(self, port, hostname, record_type, expected_address):
        transcript = ""
        try:
            result = subprocess.run(
                [
                    self.dig, "-r", f"@{LOOPBACK}", "-p", str(port),
                    f"{hostname}.", record_type, "+time=1", "+tries=1",
                    "+nosearch", "+noall", "+comments", "+answer", "+noedns",
                ],
                capture_output=True, text=True, timeout=QUERY_TIMEOUT,
            )
            transcript = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, "dig failed")
            self.assertRegex(result.stdout, r"opcode: QUERY, status: NOERROR,")
            flags = re.search(r";; flags: ([^;]*);", result.stdout)
            self.assertIsNotNone(flags, "Missing DNS response flags")
            self.assertIn("qr", flags.group(1).split())
            self.assertNotIn("tc", flags.group(1).split(), "Truncated DNS answer")
            self.assertRegex(result.stdout, r"\bANSWER: 1(?:,|\s|$)")
            records = []
            for line in result.stdout.splitlines():
                if not line.strip() or line.startswith(";"):
                    continue
                fields = line.split()
                self.assertEqual(len(fields), 5, f"Unexpected answer: {line}")
                self.assertTrue(fields[1].isdigit(), f"Invalid TTL: {line}")
                records.append((
                    fields[0].lower(), fields[2], fields[3],
                    str(ipaddress.ip_address(fields[4])),
                ))
            # Compare the entire answer, not just the presence of a null IP:
            # CNAMEs, extra addresses, missing records and duplicates all fail.
            self.assertEqual(records, [(
                f"{hostname}.", "IN", record_type,
                str(ipaddress.ip_address(expected_address)),
            )])
        except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
            self.fail(
                f"{hostname} {record_type} via {LOOPBACK}:{port}: {error}\n"
                f"{transcript}\n{self.logs()}"
            )

    def test_generated_tiers_block_both_answer_families_and_forward_controls(self):
        self.log_paths = []
        with tempfile.TemporaryDirectory(prefix="dnsmasq-integration-") as temporary:
            root = Path(temporary)
            sources = root / "src"
            sources.mkdir()
            lists = root / "lists"
            for filename, contents in {
                "safe.txt": "lgsmartad.com # SAFE: synthetic ad-zone fixture\n",
                "strict.txt": "snu.lge.com # STRICT: synthetic exact-name fixture\n",
                "zones.txt": "lge.com # ZONE: synthetic umbrella fixture\n",
            }.items():
                (sources / filename).write_text(contents, encoding="utf-8", newline="\n")
            with patch.object(build, "SRC", sources), \
                 patch.object(build, "LISTS", lists), \
                 patch.object(build, "now_utc", return_value="2026-01-01 00:00 UTC"), \
                 redirect_stdout(io.StringIO()):
                build.build()

            with self.resolver(
                root, "upstream",
                "address=/#/192.0.2.10\naddress=/#/2001:db8::10",
            ) as upstream_port:
                for tier in ("safe", "strict"):
                    with self.resolver(
                        root, tier,
                        f"server={LOOPBACK}#{upstream_port}\n"
                        f"conf-file={lists / (tier + '-dnsmasq.txt')}",
                    ) as downstream_port:
                        for hostname, safe_blocks, strict_blocks in (
                            ("lgsmartad.com", True, True),
                            ("child.lgsmartad.com", True, True),
                            ("snu.lge.com", False, True),
                            ("child.snu.lge.com", False, True),
                            ("other.lge.com", False, True),
                            ("notlge.com", False, False),
                            ("control.example", False, False),
                        ):
                            blocked = safe_blocks if tier == "safe" else strict_blocks
                            for record_type, null, forwarded in (
                                ("A", "0.0.0.0", "192.0.2.10"),
                                ("AAAA", "::", "2001:db8::10"),
                            ):
                                with self.subTest(tier=tier, hostname=hostname,
                                                  record_type=record_type):
                                    self.assert_answer(
                                        downstream_port, hostname, record_type,
                                        null if blocked else forwarded,
                                    )


if __name__ == "__main__":
    unittest.main()
