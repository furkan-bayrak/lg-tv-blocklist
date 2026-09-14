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
# parse_src strips exactly one trailing dot (FQDN root) before matching, so
# anything still ending in "." here (e.g. "host..") is malformed.
HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")
LG_SUFFIXES = ("lge.com", "lgappstv.com", "lgtvsdp.com", "lgtvcommon.com",
               "lgtviot.com", "lgthinq.com", "nextlgsdp.com", "lgsmartad.com",
               "lgsmartplatform.com", "lgeapi.com", "wiselg.com",
               "lgechannel.com", "adtvc.app", "adsdtvc.com",
               "lgunifiedsmart.com", "lggalleryplus.com", "lgsmartweb.com",
               "ueiwsp.com",
               "meethue.com")

LICENSE_LINE = "# License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"

# [REGION-SCOPED] marks one audited entry whose family LG also serves behind
# two-letter country prefixes (de.lgeapi.com, br.lgeapi.com, ...). It feeds the
# optional wildcard files only: no tagged entry is ever expanded into the six
# shipped lists, and deleting every tag leaves those six byte-identical.
REGION_TAG = "[REGION-SCOPED]"
# Bracket-anchored, so ordinary prose ("region-scoped promo beacon") and
# evidence URLs are not mistaken for a malformed tag.
REGION_TAG_PROBE = re.compile(r"\[\s*region[-_ ]?scoped", re.IGNORECASE)
REGION_CODE_RE = re.compile(r"^[a-z]{2}$")
TIER_TAG_RE = re.compile(r"\b(?:SAFE|STRICT|ZONE):")


def wildcard_header(tier: str, n: int) -> list[str]:
    """Header for the regex files. Every warning a first-time reader needs is
    above the first line of content, because the failure modes are silent."""
    return [
        f"# Title: LG TV Blocklist ({tier}) — Pi-hole regex filters",
        f"# Updated: {now_utc()}",
        f"# Entries: {n}",
        "#",
        "# PASTE THESE INTO PI-HOLE'S REGEX FILTERS, NOT AN ADLIST. An adlist takes",
        "# exact domains only and silently ignores every line in this file, leaving",
        "# you unprotected with no error shown.",
        "#   Pi-hole UI: Domains -> Add domain -> Regex   (or: pihole --regex '<line>')",
        "# AdGuard Home and uBlock Origin users do not need this file at all: the",
        f"# {tier}-adblock.txt list already wildcards via ||name^.",
        "#",
        "# Two kinds of line, both derived from src/ entries that already carry their",
        "# own evidence and annotation:",
        "#   ^<two letters>\\.family$  one audited host's family, generalised to the",
        "#                           country prefixes LG serves it from. Two-letter",
        "#                           prefixes ONLY: it never matches the family apex",
        "#                           or a longer label, so update and billing hosts",
        "#                           under the same family stay reachable.",
        "#   (\\.|^)zone$            a whole-zone anchor from src/zones.txt, whose",
        "#                           documented purpose is exactly that. STRICT only;",
        "#                           this file has none when it is the SAFE tier.",
        "# Neither kind puts a hostname into the six shipped lists.",
        "#",
        "# Optional and additive: this is not one of the six shipped lists, and never",
        "# subscribing to it, or deleting it, leaves coverage exactly as",
        f"# {tier}-domains.txt and its siblings give it today. It is also not a",
        "# replacement for them -- audited hosts with no region prefix and no zone",
        "# anchor have no line here, so keep the list subscribed.",
        LICENSE_LINE,
        "",
    ]


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
        host = line.lower()
        if host.endswith("."):
            host = host[:-1]
        if not HOSTNAME_RE.match(host):
            raise ValueError(f"{filename}:{lineno}: malformed hostname: {line!r}")
        if not any(host == suffix or host.endswith("." + suffix) for suffix in LG_SUFFIXES):
            raise ValueError(f"{filename}:{lineno}: not an LG family hostname: {host}")
        if host in seen:
            raise ValueError(f"{filename}:{lineno}: duplicate of {host} (first at line {seen[host]})")
        seen[host] = lineno
    return sorted(seen)


def region_families(filename: str) -> list[str]:
    """Family suffixes of [REGION-SCOPED] entries, for the wildcard outputs.

    The tag is explicit and never inferred from the shape of a hostname. A
    two-letter first label does not mean "country": ad.lgappstv.com is an ad
    host on the store CDN, am./ig..lge.com are unknown services, su.lge.com is
    the OTA server. Deriving the tag would emit a regex blocking every
    two-letter sibling of the store CDN and of the update server.

    Every failure here is hard, with a line number. A tag that is malformed,
    duplicated, on a line with no entry, on an entry with no tier annotation, or
    on a host with no two-letter first label to generalise raises -- silently
    ignoring one would quietly drop a family's regional coverage, or quietly
    invent one. Position within the annotation is free: entries here grow a
    trailing " | DECOMMISSIONED ..." note over time, and a tagged host getting
    decommissioned must not break the build.
    """
    families: dict[str, None] = {}
    for lineno, raw in enumerate(
            (SRC / filename).read_text(encoding="utf-8").splitlines(), 1):
        host, _, comment = raw.partition("#")
        # parse_src tolerates one trailing dot; without the same treatment here
        # the tag would emit a regex ending in an escaped dot, matching nothing.
        host = host.strip().lower().removesuffix(".")
        if not REGION_TAG_PROBE.search(comment):
            continue
        if REGION_TAG not in comment:
            raise ValueError(
                f"{filename}:{lineno}: malformed region tag in {comment.strip()!r}; "
                f"expected exactly {REGION_TAG}")
        if comment.count(REGION_TAG) > 1:
            raise ValueError(f"{filename}:{lineno}: {REGION_TAG} appears more than once")
        if not host:
            raise ValueError(
                f"{filename}:{lineno}: {REGION_TAG} on a line with no entry; the tag "
                f"belongs on an audited hostname, not in prose")
        if not TIER_TAG_RE.search(comment):
            raise ValueError(
                f"{filename}:{lineno}: {REGION_TAG} on an entry with no SAFE:/STRICT:/"
                f"ZONE: annotation; only entries that already carry evidence may be tagged")
        first, dot, rest = host.partition(".")
        if not dot or not REGION_CODE_RE.match(first):
            raise ValueError(
                f"{filename}:{lineno}: {REGION_TAG} needs a two-letter first label to "
                f"generalise, got {host!r}")
        families.setdefault(rest, None)
    return sorted(families)


def wildcard_lines(families: list[str], zones: list[str]) -> list[str]:
    """Pi-hole regex filters: region prefixes, then whole-zone anchors.

    Whole-subtree reach comes only from zones.txt. Deriving it from ordinary
    entries instead would turn an exact-name entry like lgtvsdp.com into a rule
    over every host beneath it -- which is what the adblock lists do and what
    docs/faq.md carves an exception out of, not something an exact-name
    subscriber opted into.

    re.escape is deliberately not used: it escapes '-' as '\\-', which is
    undefined in the POSIX ERE that Pi-hole's FTL compiles. HOSTNAME_RE already
    limits entries to [a-z0-9-] and dots, so escaping the dot is exact.
    """
    def pattern(host: str) -> str:
        return host.replace(".", r"\.")

    zone_set = {zone.lower() for zone in zones}

    def covered(family: str) -> bool:
        """True if a zone anchor in this file already matches the family."""
        return ".".join(family.split(".")[-2:]) in zone_set

    lines = [rf"^[a-z][a-z]\.{pattern(fam)}$"
             for fam in sorted(set(families)) if not covered(fam)]
    lines += [rf"(\.|^){pattern(zone)}$" for zone in sorted(zone_set)]
    return lines


def assert_stays_in_tier(lines: list[str], foreign: list[str]) -> None:
    """A tier's regex lines must not reach hosts that tier does not block.

    SAFE is the one that matters: su.lge.com (OTA) and am./ig..lge.com are
    STRICT entries whose first label happens to be two letters, so a tag on a
    SAFE lge.com host would silently put the update server behind a SAFE rule.
    It can only see hosts this repo lists; reach beyond them is a human call,
    recorded in CONTRIBUTING.
    """
    for line in lines:
        compiled = re.compile(line)
        for host in foreign:
            if compiled.search(host):
                raise ValueError(
                    f"wildcard line {line!r} matches {host}, which is not in this "
                    f"tier; remove the [REGION-SCOPED] tag from that family")


def compile_wildcard(tier: str, families: list[str], zones: list[str]) -> str:
    lines = wildcard_lines(families, zones)
    return "\n".join(wildcard_header(tier, len(lines)) + lines) + "\n"


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
    # Optional Pi-hole regex variants, built from the same src/ and never fed
    # back into the six lists above. Whole-subtree reach comes only from
    # zones.txt, which is STRICT-only -- so the SAFE file is region lines and
    # nothing else, and cannot block a host SAFE has not audited.
    safe_families = region_families("safe.txt")
    strict_families = region_families("strict.txt")
    if region_families("zones.txt"):
        raise ValueError("zones.txt: [REGION-SCOPED] has nothing to generalise; "
                         "zone anchors are already whole-subtree")
    safe_wildcard = wildcard_lines(safe_families, [])
    assert_stays_in_tier(safe_wildcard, strict_delta + zones)
    all_outputs["safe-wildcard.txt"] = compile_wildcard("safe", safe_families, [])
    all_outputs["strict-wildcard.txt"] = compile_wildcard(
        "strict", safe_families + strict_families, zones)
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
    # newline="\n" like the list files above: without it Python translates to
    # CRLF on a Windows checkout and `sha256sum -c SHA256SUMS` cannot read it.
    (LISTS / "SHA256SUMS").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
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
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())