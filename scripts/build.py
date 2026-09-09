#!/usr/bin/env python3
"""Compile LG TV blocklist source files into distributable formats.

Pure stdlib. Formats: plain domains, hosts (0.0.0.0), adblock (||x^).
strict = safe + strict-delta (+ zone anchors). Zones become apex lines in
domains/hosts outputs and ||zone^ in the adblock output.
"""
import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
LISTS = ROOT / "lists"
HOSTNAME_RE = re.compile(r"^(?=.{1,253}\.?$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.?$")
LG_SUFFIXES = ("lge.com", "lgappstv.com", "lgtvsdp.com", "lgtvcommon.com",
               "lgtviot.com", "lgthinq.com", "nextlgsdp.com", "lgsmartad.com",
               "lgsmartplatform.com", "lgeapi.com", "wiselg.com",
               "lgechannel.com", "adtvc.app", "adsdtvc.com",
               "lgunifiedsmart.com")

LICENSE_LINE = "# License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_src(filename: str) -> list[str]:
    """Return sorted, validated hostnames from an annotated src file.

    Raises ValueError (with line numbers) on duplicate, malformed, or
    non-LG-related hostnames.
    """
    path = SRC / filename
    seen: dict[str, int] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        host = line.lower().rstrip(".")
        if not HOSTNAME_RE.match(host):
            raise ValueError(f"{filename}:{lineno}: malformed hostname: {line!r}")
        if not host.endswith(LG_SUFFIXES):
            raise ValueError(f"{filename}:{lineno}: not an LG family hostname: {host}")
        if host in seen:
            raise ValueError(f"{filename}:{lineno}: duplicate of {host} (first at line {seen[host]})")
        seen[host] = lineno
    return sorted(seen)


def make_headers(title: str, entries: int) -> list[str]:
    return [
        f"# Title: {title}",
        f"# Updated: {now_utc()}",
        f"# Entries: {entries}",
        LICENSE_LINE,
        "",
    ]


def compile_tier(tier: str, domains: list[str], zones: list[str]) -> dict[str, str]:
    """Return output filename -> content for one tier."""
    if tier == "strict":
        domains = sorted(set(domains) | set(zones))
    title = f"LG TV Blocklist ({tier})"
    outputs: dict[str, str] = {}
    outputs[f"{tier}-domains.txt"] = "\n".join(make_headers(title, len(domains)) + domains) + "\n"
    outputs[f"{tier}-hosts.txt"] = "\n".join(
        make_headers(title, len(domains)) + [f"0.0.0.0 {d}" for d in domains]) + "\n"
    outputs[f"{tier}-adblock.txt"] = "\n".join(
        make_headers(title, len(domains)) + [f"||{d}^" for d in domains]) + "\n"
    return outputs


def load_all() -> tuple[list[str], list[str], list[str]]:
    safe = parse_src("safe.txt")
    strict_delta = parse_src("strict.txt")
    zones = parse_src("zones.txt")
    overlap = set(safe) & set(strict_delta)
    if overlap:
        raise ValueError(f"strict.txt duplicates safe.txt: {sorted(overlap)} (strict is a delta)")
    if set(zones) & set(safe):
        raise ValueError("zones.txt overlaps safe.txt — zones are strict-only")
    return safe, strict_delta, zones


def dry_run() -> dict[str, str]:
    safe, strict_delta, zones = load_all()
    all_outputs: dict[str, str] = {}
    all_outputs.update(compile_tier("safe", safe, []))
    all_outputs.update(compile_tier("strict", safe + strict_delta, zones))
    return all_outputs


def build() -> None:
    all_outputs = dry_run()
    LISTS.mkdir(exist_ok=True)
    for name, content in sorted(all_outputs.items()):
        (LISTS / name).write_text(content, encoding="utf-8", newline="\n")
    checksums = []
    for name in sorted(all_outputs):
        digest = hashlib.sha256((LISTS / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}")
    (LISTS / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    for name in sorted(all_outputs):
        print(f"wrote lists/{name}")


def check() -> None:
    safe, strict_delta, zones = load_all()
    outputs = dry_run()
    safe_n = len(safe)
    strict_n = len(set(safe) | set(strict_delta) | set(zones))
    print(f"check OK: safe={safe_n} strict={strict_n} zone-anchors={len(zones)} "
          f"outputs={len(outputs)}")
    print(f"source files: {[p.name for p in sorted(SRC.glob('*.txt'))]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile LG TV blocklists")
    parser.add_argument("mode", choices=["build", "check"], help="build writes lists/; check validates only")
    args = parser.parse_args(argv)
    try:
        if args.mode == "build":
            build()
        else:
            check()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())