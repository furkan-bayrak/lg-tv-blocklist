#!/usr/bin/env python3
"""Check whether a DNS blocker actually blocks the shipped list entries.

Usage:
    python scripts/check_blocking.py --server 192.168.1.53
    python scripts/check_blocking.py --server 192.168.1.53 --file lists/safe-domains.txt
    python scripts/check_blocking.py --domains snu.lge.com,example.com
    python scripts/check_blocking.py --domains snu.lge.com --expect-blocked
    python scripts/check_blocking.py --json

"The list is on my Pi-hole, but the TV still shows ads" has three possible
layers: the blocker is not filtering, the TV bypasses the blocker, or the TV
answers from its own cache. This tool checks the first layer only: it queries
the resolver the TV is supposed to use, over plain UDP DNS, and compares the
answer with ground truth from an independent DoH resolver.

Verdicts (one per domain):

    BLOCKED      the resolver did not return a usable address -- NXDOMAIN,
                 NOERROR without an A record, or a null/loopback sinkhole --
                 while the DoH cross-check shows the name exists. The block
                 applies on this resolver.
    DEAD         both the resolver and the cross-check say the name does not
                 exist. A stale list entry, not evidence of blocking.
    RESOLVES     the resolver returned a real address. Not blocked by DNS.
    UNREACHABLE  the resolver did not answer within --timeout. This is
                 never reported as BLOCKED: a silent resolver may be down,
                 firewalled, or slow, and silence says nothing about filtering.
    ERROR        no verdict: SERVFAIL/REFUSED, a malformed packet, an
                 inconclusive cross-check, or a name without an A record on
                 either side (delegated apex / AAAA-only).

The DoH cross-check is what makes BLOCKED and DEAD distinguishable, so it is
ON by default (dns.google). Use --cross-check cloudflare (or 1.1.1.1) to
switch providers. Without a cross-check result a failing local lookup is
reported as ERROR, never as BLOCKED.

Exit codes: 0 the check ran to completion, 1 --expect-blocked was given and
at least one domain was not confirmed BLOCKED, 2 usage or configuration
error. The script only reads lists and sends DNS queries -- it never writes.

Pure stdlib, and network access is required, so this is deliberately NOT part
of `build.py check`. scripts/test_check_blocking.py runs fully offline.
"""
import argparse
import ipaddress
import json
import os
import socket
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if sys.platform == "win32":
    import winreg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "lists" / "strict-domains.txt"

QTYPE_A = 1
QCLASS_IN = 1
RCODE_NOERROR = 0
RCODE_NXDOMAIN = 3
RCODE_NAMES = {1: "FORMERR", 2: "SERVFAIL", 4: "NOTIMP", 5: "REFUSED"}

# Verdicts, in report order.
BLOCKED, DEAD, RESOLVES, UNREACHABLE, ERROR = (
    "BLOCKED", "DEAD", "RESOLVES", "UNREACHABLE", "ERROR")

# Local resolver outcomes. NXDOMAIN/NO_ANSWER only become a verdict after a
# cross-check; the rest are already conclusive on their own.
L_ANSWERED = "answered"     # NOERROR with at least one real A record
L_SINKHOLED = "sinkholed"   # NOERROR, only null/loopback addresses
L_NXDOMAIN = "nxdomain"
L_NO_ANSWER = "no_answer"   # NOERROR, no A record
L_TIMEOUT = "timeout"       # nothing came back within the timeout
L_FAILED = "failed"         # SERVFAIL/REFUSED/... or an unparseable packet

# DoH cross-check outcomes (ground truth from an independent resolver).
X_RESOLVES = "resolves"     # NOERROR with an A record
X_EXISTS = "exists"         # NOERROR without an A record (apex/CNAME-only)
X_NXDOMAIN = "nxdomain"
X_ERROR = "error"

# Null/loopback answers: how Pi-hole, AdGuard Home and friends sinkhole.
# Queries here are A-only, but both families are listed for completeness.
SINKHOLE_ADDRS = frozenset({"0.0.0.0", "::", "127.0.0.1", "::1"})

PROVIDERS = {
    "google": ("https://dns.google/resolve?name={name}&type={rtype}", {}),
    "cloudflare": ("https://cloudflare-dns.com/dns-query?name={name}&type={rtype}",
                   {"accept": "application/dns-json"}),
}
CROSS_CHECK_ALIASES = {
    "google": "google", "8.8.8.8": "google", "dns.google": "google",
    "cloudflare": "cloudflare", "1.1.1.1": "cloudflare",
    "cloudflare-dns.com": "cloudflare",
}

ATTEMPTS = 2  # one resend: a single lost UDP datagram is common on Wi-Fi
WORKERS = 8


def new_txid() -> int:
    """Random DNS transaction id; a helper so tests can pin it."""
    return struct.unpack(">H", os.urandom(2))[0]


def build_query(name: str, txid: int) -> bytes:
    """One recursive (RD=1) A/IN query packet. Pure; raises ValueError."""
    qname = b""
    for label in name.rstrip(".").split("."):
        try:
            raw = label.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError(f"non-ASCII label {label!r}") from None
        if not raw or len(raw) > 63:
            raise ValueError(f"bad label {label!r}")
        qname += bytes([len(raw)]) + raw
    if len(qname) > 253:
        raise ValueError(f"name too long ({len(qname)} bytes)")
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    return header + qname + b"\x00" + struct.pack(">HH", QTYPE_A, QCLASS_IN)


def skip_name(data: bytes, offset: int) -> int:
    """Offset just past a DNS name (labels and/or a compression pointer)."""
    labels = 0
    while True:
        if offset >= len(data):
            raise ValueError("truncated name")
        length = data[offset]
        if length & 0xC0 == 0xC0:  # compression pointer: 2 bytes
            if offset + 2 > len(data):
                raise ValueError("truncated compression pointer")
            return offset + 2
        if length == 0:
            return offset + 1
        offset += length + 1
        labels += 1
        if labels > 127:
            raise ValueError("name has too many labels")


def parse_response(data: bytes, txid: int) -> tuple[int, list[str]]:
    """A DNS response -> (rcode, A-record addresses). Raises ValueError."""
    if len(data) < 12:
        raise ValueError("response shorter than a DNS header")
    rid, flags, qdcount, ancount = struct.unpack(">HHHH", data[:8])
    if rid != txid:
        raise ValueError(f"transaction id mismatch ({rid:#06x} != {txid:#06x})")
    rcode = flags & 0x000F
    offset = 12
    for _ in range(qdcount):
        offset = skip_name(data, offset) + 4  # + QTYPE + QCLASS
    addrs = []
    for _ in range(ancount):
        offset = skip_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError("truncated answer record")
        rtype, rclass, _ttl, rdlength = struct.unpack(
            ">HHIH", data[offset:offset + 10])
        offset += 10
        if offset + rdlength > len(data):
            raise ValueError("truncated rdata")
        if rtype == QTYPE_A and rclass == QCLASS_IN and rdlength == 4:
            addrs.append(".".join(str(byte) for byte in data[offset:offset + 4]))
        offset += rdlength
    return rcode, addrs


def local_state(rcode: int, addrs: list[str]) -> tuple[str, str]:
    """Turn a parsed local answer into (state, detail). Pure."""
    if rcode == RCODE_NXDOMAIN:
        return L_NXDOMAIN, "NXDOMAIN"
    if rcode != RCODE_NOERROR:
        name = RCODE_NAMES.get(rcode, "unknown")
        return L_FAILED, f"{name} (rcode {rcode})"
    if not addrs:
        return L_NO_ANSWER, "NOERROR without an A record"
    if all(addr in SINKHOLE_ADDRS for addr in addrs):
        return L_SINKHOLED, f"sinkholed to {'/'.join(addrs)}"
    return L_ANSWERED, "/".join(addrs)


def query_local(name: str, server: str, port: int, timeout: float,
                attempts: int = ATTEMPTS) -> tuple[str, str]:
    """Plain-UDP A query to the user's resolver. Returns (state, detail)."""
    try:
        packet = build_query(name, new_txid())
    except ValueError as exc:
        return L_FAILED, f"unusable name: {exc}"
    txid = struct.unpack(">H", packet[:2])[0]
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    malformed = ""
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            for _ in range(attempts):
                try:
                    sock.sendto(packet, (server, port))
                except OSError as exc:
                    return L_FAILED, f"cannot send to {server}:{port}: {exc}"
                try:
                    data, peer = sock.recvfrom(4096)
                except TimeoutError:
                    continue
                except ConnectionError:
                    # Windows reports an ICMP port-unreachable as a reset on
                    # the next recv: the resolver effectively did not answer.
                    continue
                except OSError as exc:
                    return L_FAILED, f"receive failed: {exc}"
                if peer[0].split("%")[0].lower() != server.split("%")[0].lower():
                    continue  # a stray datagram, not the resolver we asked
                try:
                    rcode, addrs = parse_response(data, txid)
                except ValueError as exc:
                    malformed = f"malformed response: {exc}"
                    continue
                return local_state(rcode, addrs)
    except OSError as exc:
        return L_FAILED, f"socket error: {exc}"
    if malformed:
        return L_FAILED, malformed
    return L_TIMEOUT, f"no response within {timeout:g}s after {attempts} attempts"


def classify_local(local: tuple[str, str],
                   cross: tuple[str, str] | None) -> tuple[str, str]:
    """Merge a local resolver outcome with an optional DoH cross-check.

    Pure -- this is where BLOCKED and DEAD are told apart, which is exactly
    why a local failure without a cross-check result is ERROR, not BLOCKED:
    NXDOMAIN alone cannot distinguish "my blocker filtered this" from "this
    host is dead".
    """
    state, detail = local
    if state == L_ANSWERED:
        return RESOLVES, f"resolves to {detail}"
    if state == L_SINKHOLED:
        return BLOCKED, detail  # a null answer is a deliberate sinkhole
    if state == L_TIMEOUT:
        return UNREACHABLE, detail  # silence is never evidence of filtering
    if state == L_FAILED:
        return ERROR, detail
    # L_NXDOMAIN or L_NO_ANSWER: a local failure, meaningless without truth.
    if cross is None:
        return ERROR, f"{detail} locally; no cross-check result to compare with"
    xstate, xdetail = cross
    if xstate == X_RESOLVES:
        return BLOCKED, f"{detail} locally; resolves to {xdetail} via cross-check"
    if xstate == X_EXISTS:
        if state == L_NO_ANSWER:
            return ERROR, ("no A record from the resolver or the cross-check "
                           "(delegated apex or AAAA-only); not a blocking verdict")
        return BLOCKED, f"{detail} locally; name exists via cross-check"
    if xstate == X_NXDOMAIN:
        if state == L_NXDOMAIN:
            return DEAD, "NXDOMAIN locally and via cross-check"
        return DEAD, f"{detail} locally; NXDOMAIN via cross-check"
    return ERROR, f"{detail} locally; cross-check failed ({xdetail})"


def cross_classify(payload: object) -> tuple[str, str]:
    """Map a parsed DoH JSON payload to (state, detail). Pure.

    A payload that is not a dict, or whose Answer section has the wrong
    shape, is an ERROR -- it must not abort the run (same discipline as
    verify.py's classify()).
    """
    if not isinstance(payload, dict):
        return X_ERROR, f"malformed DoH payload ({type(payload).__name__})"
    status = payload.get("Status")
    if status == RCODE_NXDOMAIN:
        return X_NXDOMAIN, "NXDOMAIN"
    if status != RCODE_NOERROR:
        return X_ERROR, f"unexpected DoH status {status!r}"
    answers = payload.get("Answer") or []
    try:
        addrs = [a.get("data", "") for a in answers if a.get("type") == QTYPE_A]
    except (AttributeError, TypeError):
        return X_ERROR, "malformed DoH answer section"
    if addrs:
        return X_RESOLVES, addrs[0]
    return X_EXISTS, "no A record (delegated apex or CNAME-only)"


def cross_lookup(name: str, provider: str = "google",
                 timeout: float = 3.0) -> tuple[str, str]:
    """DoH ground truth on an independent resolver. Returns (state, detail)."""
    template, headers = PROVIDERS[provider]
    url = template.format(name=urllib.parse.quote(name), rtype="A")
    req = urllib.request.Request(
        url, headers={"user-agent": "lg-tv-blocklist-check", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError,
            json.JSONDecodeError) as exc:
        return X_ERROR, f"{type(exc).__name__}: {exc}"
    return cross_classify(payload)


def check_one(domain: str, server: str, port: int, timeout: float,
              cross_provider: str) -> tuple[str, str]:
    """Query one domain locally and, when needed, against DoH ground truth."""
    local = query_local(domain, server, port, timeout)
    cross = None
    if local[0] in (L_NXDOMAIN, L_NO_ANSWER):
        cross = cross_lookup(domain, cross_provider, timeout)
    return classify_local(local, cross)


def check_many(domains: list[str], server: str, port: int, timeout: float,
               cross_provider: str, workers: int = WORKERS) -> dict[str, tuple[str, str]]:
    """Check every domain with a modest thread pool; order is preserved."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(
            lambda domain: check_one(domain, server, port, timeout, cross_provider),
            domains)
    return dict(zip(domains, results))


def count_verdicts(results: dict[str, tuple[str, str]]) -> dict[str, int]:
    """Verdict -> count, with all five keys present even when zero."""
    counts = {verdict: 0 for verdict in (BLOCKED, DEAD, RESOLVES, UNREACHABLE, ERROR)}
    for verdict, _ in results.values():
        counts[verdict] += 1
    return counts


def read_domains(path: Path) -> list[str]:
    """Hostnames from a built list file (comments and blanks skipped).

    Tolerates the hosts and adblock output formats as well, and keeps file
    order so the report reads like the list.
    """
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if line.startswith("0.0.0.0 "):
            line = line[len("0.0.0.0 "):].strip()
        elif line.startswith("||") and line.endswith("^"):
            line = line[2:-1]
        line = line.lower()
        if line and line not in out:
            out.append(line)
    return out


def system_resolver() -> str | None:
    """Best-effort OS resolver IP. None when it cannot be determined."""
    if sys.platform == "win32":
        return _windows_resolver()
    return _posix_resolver()


def _posix_resolver(path: Path = Path("/etc/resolv.conf")) -> str | None:
    """First usable `nameserver` entry (a 127.0.0.53 stub counts as valid)."""
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            parts = raw.split("#", 1)[0].split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                try:
                    return str(ipaddress.ip_address(parts[1]))
                except ValueError:
                    continue
    except OSError:
        return None
    return None


def _windows_resolver() -> str | None:
    """First configured DNS server from the registry (best effort)."""
    base = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
    paths = [base]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as key:
            subkeys = [winreg.EnumKey(key, index)
                       for index in range(winreg.QueryInfoKey(key)[0])]
        paths += [base + rf"\Interfaces\{name}" for name in subkeys]
    except OSError:
        pass
    for path in paths:
        for value_name in ("NameServer", "DhcpNameServer"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    raw, _ = winreg.QueryValueEx(key, value_name)
            except OSError:
                continue
            for token in str(raw).replace(",", " ").replace(";", " ").split():
                try:
                    return str(ipaddress.ip_address(token))
                except ValueError:
                    continue
    return None


def resolver_address(value: str) -> str:
    """argparse type for --server: a literal IP (v4 or v6), canonicalized."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an IP address: {value!r}") from None


def port_number(value: str) -> int:
    """argparse type for --port: 1-65535, clean error otherwise."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port out of range: {port}")
    return port


def positive_seconds(value: str) -> float:
    """argparse type for --timeout: a positive number of seconds."""
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if seconds <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {seconds:g}")
    return seconds


def cross_provider(value: str) -> str:
    """argparse type for --cross-check: provider name or its resolver IP."""
    key = value.strip().lower()
    if key in CROSS_CHECK_ALIASES:
        return CROSS_CHECK_ALIASES[key]
    raise argparse.ArgumentTypeError(
        f"unknown cross-check resolver {value!r}: use google/8.8.8.8 or "
        "cloudflare/1.1.1.1")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a DNS blocker actually blocks list entries",
        epilog="Exit codes: 0 the check ran, 1 --expect-blocked and a domain "
               "was not confirmed BLOCKED, 2 usage/config error.")
    parser.add_argument("--server", type=resolver_address, default=None,
                        help="resolver IP to query (default: the OS resolver)")
    parser.add_argument("--port", type=port_number, default=53,
                        help="resolver port (default: 53)")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help=f"list file to check (default: {DEFAULT_FILE.name})")
    parser.add_argument("--domains", metavar="D1,D2", default=None,
                        help="comma-separated domains to check instead of --file")
    parser.add_argument("--timeout", type=positive_seconds, default=3.0,
                        help="seconds to wait per query (default: 3.0)")
    parser.add_argument("--cross-check", type=cross_provider, default="google",
                        metavar="HOST",
                        help="DoH resolver for ground truth: google/8.8.8.8 or "
                             "cloudflare/1.1.1.1 (default: google; the cross-check "
                             "is ON by default because BLOCKED and DEAD cannot be "
                             "told apart without it)")
    parser.add_argument("--json", action="store_true",
                        help="write a JSON report to stdout")
    parser.add_argument("--expect-blocked", action="store_true",
                        help="exit 1 unless every checked domain is BLOCKED")
    args = parser.parse_args(argv)

    if args.domains is not None:
        domains: list[str] = []
        for token in args.domains.split(","):
            domain = token.strip().lower()
            if domain and domain not in domains:
                domains.append(domain)
        if not domains:
            print("ERROR: --domains contained no domain names", file=sys.stderr)
            return 2
    else:
        if not args.file.is_file():
            print(f"ERROR: no such file: {args.file} (run build.py build first)",
                  file=sys.stderr)
            return 2
        domains = read_domains(args.file)
        if not domains:
            print(f"ERROR: no entries parsed from {args.file}", file=sys.stderr)
            return 2

    server = args.server or system_resolver()
    if not server:
        print("ERROR: cannot determine the OS resolver; pass --server <ip>",
              file=sys.stderr)
        return 2

    print(f"checking {len(domains)} domain(s) against {server}:{args.port} "
          f"(cross-check: {args.cross_check})...", file=sys.stderr)
    results = check_many(domains, server, args.port, args.timeout, args.cross_check)
    counts = count_verdicts(results)

    if args.json:
        json.dump({
            "server": server,
            "port": args.port,
            "cross_check": args.cross_check,
            "counts": counts,
            "results": [{"domain": domain,
                         "classification": results[domain][0],
                         "detail": results[domain][1]} for domain in domains],
        }, sys.stdout, indent=2)
        print()
    else:
        for domain in domains:
            verdict, detail = results[domain]
            print(f"{verdict:<11} {domain:<45} {detail}")
    print("  ".join(f"{verdict}={counts[verdict]}" for verdict in counts),
          file=sys.stderr)

    if args.expect_blocked:
        failed = [domain for domain in domains if results[domain][0] != BLOCKED]
        if failed:
            print(f"ERROR: {len(failed)} of {len(domains)} domain(s) not "
                  f"confirmed BLOCKED: {', '.join(failed)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
