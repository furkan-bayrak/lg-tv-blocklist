"""Offline apply and rollback tests. No host firewall, Luna, network or clock calls."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "examples/webos-hooks"
APPLY = "02-block-dns-egress.sh"
ROLLBACK = "rollback-dns-egress.sh"
RESOLVER = "192.168.1.53"
GATEWAY = "192.168.1.1"
SUCCESS = "targeted DNS-egress rules absent"


def nat_rules(resolver):
    return [["!", "-d", "127.0.0.0/8", "-p", proto, "--dport", "53", "-j", "DNAT",
             "--to-destination", f"{resolver}:53"] for proto in ("udp", "tcp")]


V4_DROP = [["-p", proto, "--dport", "853", "-j", "DROP"] for proto in ("tcp", "udp")]
V6_DROP = [["!", "-d", "::1/128", "-p", proto, "--dport", port, "-j", "DROP"]
           for port in ("53", "853") for proto in ("udp", "tcp")]
UNRELATED = ["-p", "tcp", "--dport", "22", "-j", "ACCEPT"]
FIREWALL = '''
import json
import os
import sys
from pathlib import Path

family, *args = sys.argv[1:]
table = "filter"
if args[0] == "-t":
    table = args[1]
    args = args[2:]
operation, chain, *rule = args
root = Path(os.environ["SANDBOX"])
path = root / "firewall.json"
state = json.loads(path.read_text())
key = f"{family}:{table}"
rules = state[key]
if (operation, chain) == ("-L", "-n"):
    sys.exit(0)
assert chain == "OUTPUT", args
for failed_key, failed_operation, failed_rule, status in json.loads(os.environ["FAULTS"]):
    if key == failed_key and operation == failed_operation and (failed_rule is None or rule == failed_rule):
        sys.exit(status)
if operation == "-C":
    sys.exit(0 if rule in rules else 1)
if operation == "-S":
    print("-P OUTPUT ACCEPT")
    for present in rules:
        print("-A OUTPUT " + " ".join(present))
    sys.exit(0)
if operation == "-A":
    rules.append(rule)
elif operation == "-D" and rule in rules:
    rules.remove(rule)
else:
    sys.exit(1)
path.write_text(json.dumps(state))
'''
TIMEOUT = '''
case "$TIMEOUT_MODE" in
    legacy) [ "$1" = -t ] || exit 2; shift ;;
    modern) [ "$1" != -t ] || exit 2 ;;
    *) exit 2 ;;
esac
if [ "$1" = 1 ] && [ "$2" = true ] && [ "$#" = 2 ]; then exit 0; fi
[ "$1" = 5 ] || exit 2
LUNA_BOUND="$1"
export LUNA_BOUND
shift
exec "$@"
'''


@unittest.skipUnless(os.name == "posix", "requires a POSIX shell sandbox")
class DnsEgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dns-hook-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.shell = shutil.which("sh")
        self.fixture = self.root / "firewall.py"
        self.fixture.write_text(FIREWALL, encoding="utf-8")
        self.luna_calls = self.root / "luna-calls"
        self.luna_calls.write_text("", encoding="utf-8")
        for name, family in (("iptables", "v4"), ("ip6tables", "v6")):
            self.stub(name, f"exec {shlex.quote(sys.executable)} {shlex.quote(str(self.fixture))} {family} \"$@\"")
        for name in ("awk", "head"):
            path = shutil.which(name)
            self.assertIsNotNone(path, f"required POSIX tool: {name}")
            self.stub(name, f"exec {shlex.quote(path)} \"$@\"")
        self.stub("ip", 'case "$*" in route) printf "%s" "$GATEWAY_ROUTE";; "-6 route show default") echo "default via fe80::1";; *) exit 2;; esac')
        self.stub("date", 'printf "offline-clock\\n"')
        self.stub("logger", "exit 0")
        self.stub("luna-send", '''
            printf '%s\n' "${LUNA_BOUND:-unbounded}" >> "$SANDBOX/luna-calls"
            [ "${LUNA_BOUND:-}" = 5 ] || exit 2
            printf '%s\n' "$LUNA_JSON_FIXTURE"
        ''')
        self.reset_rules()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        path.chmod(0o700)

    def reset_rules(self, *, nat=(), v4=(), v6=()):
        self.rules_file.write_text(json.dumps({"v4:nat": list(nat), "v4:filter": list(v4),
                                               "v6:filter": list(v6)}), encoding="utf-8")

    @property
    def rules_file(self):
        return self.root / "firewall.json"

    def rules(self):
        return json.loads(self.rules_file.read_text(encoding="utf-8"))

    def run_hook(self, name, *, payload=None, timeout_mode="modern", gateway=GATEWAY,
                 override="", allow_public=False, v4=True, v6=True, faults=()):
        script = self.root / name
        source = (HOOKS / name).read_text(encoding="utf-8")
        # Relocate only the fixed log destination. Restrict PATH and override
        # all effectful tools, even when modelling a missing firewall binary.
        log = shlex.quote(str(self.root / "apply.log"))
        source = source.replace("LOG=/var/log/02-block-dns-egress.log", f"LOG={log}")
        source = source.replace("LOG=/tmp/02-block-dns-egress.log", f"LOG={log}")
        script.write_text(source, encoding="utf-8")
        if timeout_mode == "missing":
            (self.bin / "timeout").unlink(missing_ok=True)
        else:
            self.stub("timeout", TIMEOUT)
        env = {
            "PATH": str(self.bin), "LC_ALL": "C", "SANDBOX": str(self.root),
            "TIMEOUT_MODE": timeout_mode, "FAULTS": json.dumps(faults),
            "IPTABLES": str(self.bin / ("iptables" if v4 else "missing-v4")),
            "IP6TABLES": str(self.bin / ("ip6tables" if v6 else "missing-v6")),
            "LUNA_SEND": str(self.bin / "luna-send"), "RESOLVER_IP": override,
            "ALLOW_NON_LOCAL_RESOLVER": "1" if allow_public else "0",
            "GATEWAY_ROUTE": f"default via {gateway} dev eth0\n" if gateway else "",
            "LUNA_JSON_FIXTURE": payload if payload is not None else json.dumps({"dns1": RESOLVER}),
        }
        return subprocess.run([self.shell, script], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=10, check=False)

    def assert_clean_rollback(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn(SUCCESS, result.stdout)

    def assert_incomplete_rollback(self, result):
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertNotIn(SUCCESS, result.stdout)
        self.assertIn("rollback incomplete or unverified", result.stderr)

    def test_both_timeout_forms_and_json_layouts_discover_configured_dns(self):
        payloads = (
            f'{{"dns1":"{RESOLVER}"}}', f'{{"dns1" : "{RESOLVER}"}}',
            f'{{"dns1"\t:\t"{RESOLVER}"}}', f'{{\n  "dns1"\n :\n "{RESOLVER}"\n}}',
        )
        for mode in ("legacy", "modern"):
            for payload in payloads:
                with self.subTest(mode=mode, payload=payload):
                    self.luna_calls.write_text("", encoding="utf-8")
                    result = self.run_hook(APPLY, payload=payload, timeout_mode=mode)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    self.assertEqual(self.rules()["v4:nat"], nat_rules(RESOLVER))
                    self.assert_clean_rollback(self.run_hook(ROLLBACK, payload=payload, timeout_mode=mode))
                    self.assertFalse(any(self.rules().values()))
                    self.assertEqual(self.luna_calls.read_text().splitlines(), ["5", "5"])

    def test_missing_or_unsupported_timeout_never_calls_luna(self):
        for mode in ("missing", "unsupported"):
            with self.subTest(mode=mode):
                result = self.run_hook(APPLY, timeout_mode=mode)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("skipping connectionmanager DNS discovery", result.stderr)
                self.assertEqual(self.rules()["v4:nat"], nat_rules(GATEWAY))
                rollback = self.run_hook(ROLLBACK, timeout_mode=mode)
                self.assert_clean_rollback(rollback)
                self.assertIn("skipping connectionmanager DNS discovery", rollback.stderr)
                self.assertFalse(any(self.rules().values()))
                self.assertEqual(self.luna_calls.read_text(), "")

    def test_missing_or_unusable_dns1_falls_back_but_bad_quad_is_refused(self):
        for payload in ('{}', '{"dns1":53}', '{"dns1":"dns.example"}',
                        '{"dns1":"2001:db8::53"}', '{"dns1":"0.0.0.0"}'):
            with self.subTest(payload=payload):
                result = self.run_hook(APPLY, payload=payload)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(self.rules()["v4:nat"], nat_rules(GATEWAY))
                self.assert_clean_rollback(self.run_hook(ROLLBACK, payload=payload))
        payload = '{"dns1":"192.168.1.256"}'
        result = self.run_hook(APPLY, payload=payload, allow_public=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a dotted-quad IPv4 address", result.stdout)
        self.assertEqual(self.rules()["v4:nat"], [])
        self.assert_incomplete_rollback(self.run_hook(ROLLBACK, payload=payload))
        self.assertFalse(any(self.rules().values()))

    def test_explicit_old_address_overrides_discovery_and_supports_rollback(self):
        override = "198.51.100.53"
        result = self.run_hook(APPLY, override=override)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.rules()["v4:nat"], [])
        result = self.run_hook(APPLY, override=override, allow_public=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.rules()["v4:nat"], nat_rules(override))
        self.assert_clean_rollback(self.run_hook(ROLLBACK, override=override))
        self.assertFalse(any(self.rules().values()))
        self.assertEqual(self.luna_calls.read_text(), "")

    def test_idempotent_apply_and_verified_duplicate_removal_keep_unrelated_rules(self):
        self.reset_rules(v4=[UNRELATED], v6=[UNRELATED])
        for _ in range(2):
            result = self.run_hook(APPLY, override=RESOLVER)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("IPv6 DNS egress blocked", result.stdout)
        self.assertEqual(self.rules(), {"v4:nat": nat_rules(RESOLVER), "v4:filter": [UNRELATED, *V4_DROP],
                                        "v6:filter": [UNRELATED, *V6_DROP]})
        self.reset_rules(nat=nat_rules(RESOLVER) * 2, v4=[UNRELATED, *V4_DROP * 2],
                         v6=[UNRELATED, *V6_DROP * 2])
        for _ in range(2):
            self.assert_clean_rollback(self.run_hook(ROLLBACK, override=RESOLVER))
            self.assertEqual(self.rules(), {"v4:nat": [], "v4:filter": [UNRELATED], "v6:filter": [UNRELATED]})

    def test_partial_ipv6_apply_never_logs_ipv6_or_overall_success(self):
        result = self.run_hook(APPLY, override=RESOLVER, faults=[("v6:filter", "-A", V6_DROP[0], 1)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("IPv6 DNS egress protection incomplete", result.stdout)
        self.assertNotIn("IPv6 DNS egress blocked", result.stdout)
        self.assertNotIn("OK:", result.stdout)
        self.assertEqual(self.rules()["v4:nat"], nat_rules(RESOLVER))
        self.assertEqual(self.rules()["v6:filter"], V6_DROP[1:])

    def test_failed_deletion_keeps_remaining_rule_but_cleans_other_targets(self):
        self.reset_rules(nat=nat_rules(RESOLVER), v4=V4_DROP, v6=V6_DROP)
        result = self.run_hook(ROLLBACK, override=RESOLVER, faults=[("v6:filter", "-D", V6_DROP[0], 1)])
        self.assert_incomplete_rollback(result)
        self.assertIn("failed to delete", result.stderr)
        self.assertEqual(self.rules(), {"v4:nat": [], "v4:filter": [], "v6:filter": V6_DROP[:1]})

    def test_failed_table_inspection_or_rule_check_cannot_claim_complete_rollback(self):
        for op, rule, status, remaining in (("-S", None, 1, V4_DROP), ("-C", V4_DROP[0], 2, V4_DROP[:1])):
            with self.subTest(operation=op):
                self.reset_rules(nat=nat_rules(RESOLVER), v4=V4_DROP, v6=V6_DROP)
                result = self.run_hook(ROLLBACK, override=RESOLVER, faults=[("v4:filter", op, rule, status)])
                self.assert_incomplete_rollback(result)
                self.assertEqual(self.rules(), {"v4:nat": [], "v4:filter": remaining, "v6:filter": []})

    def test_missing_ipv4_tool_still_cleans_ipv6_without_claiming_complete_rollback(self):
        self.reset_rules(nat=nat_rules(RESOLVER), v4=V4_DROP, v6=V6_DROP)
        self.assert_incomplete_rollback(self.run_hook(ROLLBACK, v4=False))
        self.assertEqual(self.rules(), {"v4:nat": nat_rules(RESOLVER), "v4:filter": V4_DROP, "v6:filter": []})

    def test_missing_ipv6_tool_or_unknown_resolver_reports_incomplete_rollback(self):
        self.reset_rules(nat=nat_rules(RESOLVER), v4=V4_DROP, v6=V6_DROP)
        self.assert_incomplete_rollback(self.run_hook(ROLLBACK, override=RESOLVER, v6=False))
        self.assertEqual(self.rules(), {"v4:nat": [], "v4:filter": [], "v6:filter": V6_DROP})
        self.reset_rules(nat=nat_rules(RESOLVER), v4=V4_DROP, v6=V6_DROP)
        self.assert_incomplete_rollback(self.run_hook(ROLLBACK, payload="{}", gateway=""))
        self.assertEqual(self.rules(), {"v4:nat": nat_rules(RESOLVER), "v4:filter": [], "v6:filter": []})


if __name__ == "__main__":
    unittest.main()
