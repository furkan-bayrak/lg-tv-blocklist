# Contributing

Thanks for helping maintain the LG TV blocklist. Two ground rules:

## 1. Evidence over guesses

This list is built from empirical observation, not speculation. Before adding
a domain, collect evidence:

- **Querylog**: AdGuard/Pi-hole log line showing the domain, who queried it,
  and when (a single random hit is not enough; boot-burst or heartbeat
  patterns are ideal).
- **Capture**: `dns.qry.name` or TLS SNI from a packet capture.
- **Repro**: what you did to trigger it (power-on, standby, app launch).

If you only have a hunch, open an issue with the `new-domain` template
instead of a PR — maintainers can verify from their own probes.

**Check the domain still exists.** `python scripts/verify.py` resolves every
shipped entry over DNS-over-HTTPS and reports which are NXDOMAIN, so a dead
host gets annotated deliberately instead of sitting in the list unnoticed. DoH
rather than a plain lookup is the whole point: you run a DNS blocker that
sinkholes these exact names, so `dig`/`nslookup` hands your own blocklist back
to you with every entry apparently dead. Add `--cross-check` to confirm each
finding on a second provider, and `--fail-on-dead` to exit non-zero. It needs
network access, so it is not part of `build.py check`; its own logic is tested
offline by `scripts/test_verify.py`.

**Regional query logs welcome:** include the region, timestamp, and client
(TV model/name). Region-prefixed entries (`de.`, `us.`) can be extended with
evidence from your region — regional coverage is the main gap in this list.

**Datacentre clusters.** `eic` (Europe), `aic` (Americas) and `kic` (Korea)
front the same service from three continents, independently of country codes.
When you add or verify a clustered host, probe all three and include every one
that resolves — submitting only the cluster your own TV uses is how this list
came to be missing 53 live endpoints. A twin found by probing is DNS-existence
evidence, so it belongs in `strict.txt` tagged `weak` even where its sibling is
SAFE — unless the twin's sibling is a non-weak STRICT entry, in which case the
twin inherits that severity: `eic.lgtviot.com` is SAFE because it was observed,
while `aic.`/`kic.` stay `weak` until a querylog or capture from that continent
lands. See
[methodology](docs/methodology.md#dns-log-correlation).
New region prefixes must also be added to `SOURCE_REGION_LABELS` in
`scripts/localize.py`; otherwise `localize.py` silently leaves those entries
untouched.

## 2. Edit src/, never lists/

- `src/safe.txt` — telemetry/ad hostnames that are safe for stock TVs.
- `src/strict.txt` — the DELTA over safe (updates, ThinQ, LG Channels,
  weak-evidence entries). Do not repeat safe entries here.
- `src/zones.txt` — strict-only family apexes for whole-zone blocking in the
  adblock format.

Every line needs an inline annotation — format, tags, and examples in
[Annotated domains](#annotated-domains) below.

CI validates every PR that touches `src/` or `scripts/` — structural
violations (malformed, duplicate, or non-LG hostnames) fail the build;
semantic tier placement is reviewed by maintainers. The generated `lists/`
directory is off-limits to PRs (CI rejects changes to it) — edit `src/`
instead.

## Format semantics

Matching differs per generated format:

- `-domains.txt` / `-hosts.txt`: **exact-name** — `snu.lge.com` blocks that
  host only, not the whole zone.
- `-adblock.txt`: `||snu.lge.com^` also matches subdomains of that name.
- Generated `-adblock.txt` files start with `#` metadata headers (title,
  date, entry count, license). AdGuard Home and uBlock Origin both treat
  those lines as comments; `!` is the canonical adblock comment prefix, so
  use `!` for comments when you extend a list in a custom filter.
- STRICT zone anchors (see `src/zones.txt`) only achieve whole-zone blocking
  in the adblock format; in domains/hosts they block the apex domain.

All three source files use exact-name, lowercase, wildcard-free entries
(see [section 2](#2-edit-src-never-lists)): `src/safe.txt` (SAFE),
`src/strict.txt` (STRICT delta), `src/zones.txt` (STRICT-only zone
anchors). So `-domains.txt` / `-hosts.txt` subdomain coverage depends on
enumeration. In the adblock format, zone anchors match region-prefixed
subdomains (`de.`, `us.`, …) — that is why STRICT is region-complete there
for the families it anchors (the `lgtvsdp.com` time family is anchored
nowhere and stays reachable by design), while the exact-name formats cover
only the region prefixes present. Extending regional coverage is covered in
[section 1](#1-evidence-over-guesses).

## Annotated domains

The source of truth is annotated: `src/safe.txt`, `src/strict.txt`,
`src/zones.txt`. Reading the comments there tells you what every entry does
and the evidence behind it; the [tier
table](README.md#which-list-should-i-use) in the README summarizes the
trade-offs.

Every line needs an inline annotation:

    snu.lge.com # STRICT: firmware OTA check server

Line format: hostname, space, `#`, space, `TAG: short description`. The
description names the function; entries with hard evidence add it after an
em-dash (`cdpbeacon.lgtvcommon.com # SAFE: ... (6-min heartbeat pattern
observed)`). Tags: `SAFE`, `STRICT`, `ZONE` (e.g. `lge.com # ZONE: umbrella
zone — kills all lge.com subdomains in adblock format`). Lowercase only, no
trailing dot, no wildcards — this list is exact-name (see [Format
semantics](#format-semantics)). Weak-evidence entries are tagged `weak` and
belong in strict.txt by policy.

One further tag is structural rather than evidential. `[REGION-SCOPED]`
anywhere in the annotation marks an entry whose family LG also serves behind
two-letter country prefixes (`de.lgeapi.com`, `br.lgeapi.com`, …):

    de.nextlgsdp.com # SAFE: SDP region endpoint, telemetry [REGION-SCOPED]

It feeds the optional `lists/*-wildcard.txt` regex files and nothing else. The
six shipped lists are byte-identical with every tag deleted, and a test asserts
exactly that. Rules:

- Tag only an entry that already carries its own evidence and annotation. The
  tag adds regional reach to a host that was audited; it never introduces a
  family, and no untagged hostname is ever generalised. Position in the
  annotation is free — entries grow a trailing `| DECOMMISSIONED …` note over
  time, and that must not collide with the tag.
- The first label must be a two-letter code to generalise. A two-letter label
  is **not** proof of one: `ad.lgappstv.com` is an ad host on the store CDN and
  `su.lge.com` is the OTA server, so neither is tagged — tagging them would
  emit a regex covering every two-letter sibling of the store CDN and of the
  update server.
- **Nothing tagged in `safe.txt` may reach a host listed outside SAFE.** The
  build compiles each SAFE regex line and errors if it matches any STRICT entry
  or zone apex — `su.lge.com` and `am.`/`ig..lge.com` are two letters wide, so a
  tag on an `lge.com` host would otherwise put the OTA server behind a SAFE
  rule. Such a family belongs in `strict.txt`, or untagged.
- **SDP time/apps families never generalise (`lgtvsdp.com`, `nextlgsdp.com`).**
  Their region-prefixed hosts (`at.`/`de.`/`us.lgtvsdp.com`, `de.nextlgsdp.com`)
  are the TV's time-sync channel on some models, and generalising them breaks
  TV clocks — and store/app TLS with them (repo issue #6; Reddit Austria
  report; hagezi/dns-blocklists#11438). Keep such hosts as exact-name entries
  with their own evidence; the build hard-errors on a `[REGION-SCOPED]` tag in
  either family (`FORBIDDEN_REGION_FAMILIES`). The FAQ's [store
  allowlist](docs/faq.md#i-want-strict-but-keep-the-lg-content-store) carves
  the region hosts of these families back out — the same rule seen from the
  other direction.
- **Never list the bare `lgtvsdp.com` apex as an entry.** In the exact-name
  formats it blocks nothing (delegated apex, SOA-only), but the adblock output
  emits `||lgtvsdp.com^`, which covers every `<cc>.lgtvsdp.com` time host in
  every country. The build hard-errors on it in any `src/` file
  (`FORBIDDEN_APEX_ENTRIES`).
- `zones.txt` is scanned only to reject tags: its entries are apexes with
  nothing to generalise, and whole-subtree reach in the regex files comes from
  that file alone. A tag there is a build error, never a no-op.
- A malformed tag, a duplicate tag, a tag on a line with no entry, a tag on an entry with no
  `SAFE:`/`STRICT:`/`ZONE:` annotation, a tag on a host with no two-letter
  first label, or a forbidden family are all hard build errors with a line
  number. Silently skipping one would quietly drop a family's regional
  coverage, or quietly invent one.

## Workflow

1. Fork, branch off `main`.
2. Edit one or more files under `src/`.
3. Run `python3 scripts/build.py check && python3 scripts/test_build.py` locally
   (requires Python 3.10+ — the scripts use modern union type syntax).
4. Open the PR. The merge job regenerates `lists/` automatically — never
   commit generated files yourself.

## License

Content is CC BY 4.0, scripts MIT — see LICENSE and LICENSE-MIT.
