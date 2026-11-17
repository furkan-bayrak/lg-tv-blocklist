#!/usr/bin/env python3
"""Check blocklist entries' A-record answers using DNS-over-HTTPS (A-only).

Usage:
    python scripts/verify.py [--file lists/strict-domains.txt] [--out docs/verification.md]
    python scripts/verify.py --cross-check        # attempt a 2nd provider for non-LIVE only
    python scripts/verify.py --fail-on-dead       # exit 1 if anything is NXDOMAIN

Why DoH and not a normal lookup: anyone maintaining this list is, by
definition, running a DNS blocker that sinkholes these exact names, and a VPN
may force all port-53 traffic to its own resolver. A plain lookup would then
report the maintainer's own blocklist back at them -- every entry "dead". DoH
runs over 443 to a named resolver, so neither a Pi-hole, an upstream port-53
redirect, nor a VPN's resolver can intercept it.

Classification matters as much as the lookup:

    LIVE      NOERROR with an A record.
    NO_A      NOERROR without an A record. This does not establish delegation,
              retirement, current functionality, or AAAA reachability.
    NXDOMAIN  the resolver reports that the name does not exist.
    ERROR     lookup failure or provider disagreement; inconclusive.

Only A records are queried, not AAAA records. These results do not test TV
routing, TV caches, or feature compatibility. With --cross-check, a second
provider is attempted only for non-LIVE findings; agreement is not guaranteed.
Review DNS findings alongside contact, purpose, and blocking-test evidence
before changing a rule. Neither NO_A nor NXDOMAIN alone proves retirement.

Pure stdlib, like the rest of scripts/. Network access is required, so this is
deliberately NOT part of `build.py check`.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "lists" / "strict-domains.txt"

PROVIDERS = {
    "google": ("https://dns.google/resolve?name={name}&type={rtype}", {}),
    "cloudflare": ("https://cloudflare-dns.com/dns-query?name={name}&type={rtype}",
                   {"accept": "application/dns-json"}),
}
# DNS RCODEs we care about; anything else is reported verbatim as an error.
RCODE_NOERROR = 0
RCODE_NXDOMAIN = 3
A_RECORD = 1

LIVE, NO_A, NXDOMAIN, ERROR = "LIVE", "NO_A", "NXDOMAIN", "ERROR"


def classify(payload: object) -> tuple[str, str]:
    """Map a DoH JSON response to (classification, detail). Pure -- no network.

    Kept separate from the fetch so the interesting logic is testable without
    touching the network.
    """
    if not isinstance(payload, dict):
        # Valid JSON is not necessarily an object: a captive portal or a wrong
        # endpoint can answer with [] or a bare string. Inconclusive -- never a
        # verdict about the name.
        return ERROR, f"non-object DoH response: {type(payload).__name__}"
    status = payload.get("Status")
    if status == RCODE_NXDOMAIN:
        return NXDOMAIN, "name does not exist"
    if status != RCODE_NOERROR:
        return ERROR, f"rcode {status}"
    answers = payload.get("Answer") or []
    addrs = [a.get("data", "") for a in answers if a.get("type") == A_RECORD]
    if addrs:
        return LIVE, addrs[0]
    return NO_A, "NOERROR without an A record"


def resolve(name: str, provider: str = "google", rtype: str = "A",
            timeout: float = 15.0) -> tuple[str, str]:
    """DoH-resolve one name. Returns (classification, detail)."""
    template, headers = PROVIDERS[provider]
    url = template.format(name=urllib.parse.quote(name), rtype=rtype)
    req = urllib.request.Request(url, headers={"user-agent": "lg-tv-blocklist-verify",
                                               **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return classify(json.loads(resp.read().decode("utf-8")))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError,
            UnicodeDecodeError, AttributeError, TypeError) as exc:
        # UnicodeDecodeError (a ValueError): a malformed body must not abort
        # the whole run -- classify this entry as ERROR like any other failure.
        # AttributeError/TypeError: a JSON payload of an unexpected shape (e.g.
        # a captive portal returning [] or nested types that are not objects)
        # must not crash the run either; classify() handles the plain
        # non-object case, this catch is the backstop for the rest.
        return ERROR, f"{type(exc).__name__}: {exc}"


def read_entries(path: Path) -> list[str]:
    """Hostnames from a built list file (comments and blanks skipped)."""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        # Tolerate hosts ("0.0.0.0 name"), adblock ("||name^") and dnsmasq
        # ("address=/name/#") formats too; without the dnsmasq parse
        # the whole rule would be resolved as if it were a hostname.
        if line.startswith("0.0.0.0 "):
            line = line[len("0.0.0.0 "):].strip()
        elif line.startswith("||") and line.endswith("^"):
            line = line[2:-1]
        elif line.startswith("address=/") and "/" in line[len("address=/"):]:
            # Multi-name rules (address=/a/b/#): only the first domain is kept.
            line = line[len("address=/"):].partition("/")[0]
        out.append(line)
    return sorted(set(out))


def verify(names: list[str], workers: int, cross_check: bool) -> dict[str, tuple[str, str]]:
    """Query A records; optionally try a 2nd provider for non-LIVE results only."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(names, pool.map(lambda n: resolve(n, "google"), names)))
    if not cross_check:
        return results
    # Only re-check the interesting ones: a false NXDOMAIN is the costly error,
    # since acting on it would delete a live entry.
    suspect = [n for n, (cls, _) in results.items() if cls != LIVE]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        second = dict(zip(suspect, pool.map(lambda n: resolve(n, "cloudflare"), suspect)))
    for name, (cls, detail) in second.items():
        first, first_detail = results[name]
        diagnostics = (f"google={first} ({first_detail}); "
                       f"cloudflare={cls} ({detail})")
        if ERROR in (first, cls) or cls != first:
            results[name] = (ERROR, diagnostics)
        else:
            results[name] = (cls, diagnostics)
    return results


def render(results: dict[str, tuple[str, str]], cross_check: bool) -> str:
    """Markdown report, newest-run-wins (regenerate rather than hand-edit)."""
    buckets: dict[str, list[str]] = {LIVE: [], NO_A: [], NXDOMAIN: [], ERROR: []}
    for name, (cls, _) in sorted(results.items()):
        buckets[cls].append(name)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Entry verification",
        "",
        f"Generated by `scripts/verify.py` on {stamp}"
        + (" (second-provider checks attempted for non-LIVE findings only)." if cross_check
           else ". Re-run with `--cross-check` to attempt a second provider for non-LIVE findings only."),
        "",
        "Resolution is done over DNS-over-HTTPS so that a maintainer's own "
        "Pi-hole/AdGuard, an upstream port-53 redirect, or a VPN resolver cannot "
        "sinkhole these names and make live entries look dead.",
        "",
        "A-only diagnostic: queries IPv4 address answers, not AAAA records. "
        "It does not test TV routing, TV caches, or feature compatibility.",
        "",
        "| Result | Count | Meaning |",
        "|---|---|---|",
        f"| LIVE | {len(buckets[LIVE])} | Has an A record. |",
        f"| NO_A | {len(buckets[NO_A])} | NOERROR without an A record. |",
        f"| NXDOMAIN | {len(buckets[NXDOMAIN])} | Does not exist. |",
        f"| ERROR | {len(buckets[ERROR])} | Lookup failed or providers disagreed. |",
        "",
    ]
    for cls, blurb in (
        (NXDOMAIN, "The queried resolver(s) reported that these names do not exist. "
                   "This does not establish retirement; review dated DNS findings "
                   "and contact, purpose, and blocking-test evidence before changing rules."),
        (NO_A, "NOERROR without an A record does not establish delegation, retirement, "
               "current functionality, or AAAA reachability. Review the evidence "
               "before deciding whether a rule should change."),
        (ERROR, "Inconclusive — review the lookup diagnostics before drawing conclusions."),
    ):
        if not buckets[cls]:
            continue
        lines += [f"## {cls} ({len(buckets[cls])})", "", blurb, ""]
        lines += [f"- `{name}` — {results[name][1]}" for name in buckets[cls]]
        lines.append("")
    lines += [f"## LIVE ({len(buckets[LIVE])})", "",
              "Listed by count only — see the built lists for the names.", ""]
    return "\n".join(lines)


def worker_count(value: str) -> int:
    """argparse type for --workers: a positive int, clean error otherwise."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="A-only blocklist diagnostic via DNS-over-HTTPS (IPv4 address answers)",
        epilog="Does not test AAAA filtering, TV routing, TV caches, or feature compatibility. "
               "An optional second-provider check is attempted for non-LIVE findings only.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help=f"list to verify (default: {DEFAULT_FILE.name})")
    parser.add_argument("--out", type=Path, default=None,
                        help="write a markdown report here instead of stdout")
    parser.add_argument("--cross-check", action="store_true",
                        help="attempt a second provider for non-LIVE findings only (A records)")
    parser.add_argument("--workers", type=worker_count, default=12,
                        help="concurrent lookups (default: 12)")
    parser.add_argument("--fail-on-dead", action="store_true",
                        help="exit 1 if any entry is NXDOMAIN")
    args = parser.parse_args(argv)

    # This tool never edits lists: refuse an --out that would overwrite the
    # input file or anything under lists/ before any lookup or write happens.
    if args.out:
        target = args.out.resolve()
        if target == args.file.resolve() or (ROOT / "lists").resolve() in target.parents:
            print(f"ERROR: refusing --out {args.out}: it would overwrite the input "
                  "file or a shipped list", file=sys.stderr)
            return 2

    if not args.file.is_file():
        print(f"ERROR: no such file: {args.file} (run build.py build first)",
              file=sys.stderr)
        return 2
    names = read_entries(args.file)
    if not names:
        print(f"ERROR: no entries parsed from {args.file}", file=sys.stderr)
        return 2
    print(f"verifying A records (A-only) for {len(names)} entries from {args.file.name} over DoH...",
          file=sys.stderr)
    results = verify(names, args.workers, args.cross_check)
    report = render(results, args.cross_check)
    if args.out:
        args.out.write_text(report, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    counts: dict[str, int] = {}
    for cls, _ in results.values():
        counts[cls] = counts.get(cls, 0) + 1
    print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)
    if args.fail_on_dead and counts.get(NXDOMAIN):
        print(f"ERROR: {counts[NXDOMAIN]} entries are NXDOMAIN", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
