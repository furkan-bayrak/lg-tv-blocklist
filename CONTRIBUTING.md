# Contributing

Thanks for helping maintain the LG TV blocklist. Two ground rules:

## 1. Evidence over guesses

Separate three evidence questions; none substitutes for the others:

- **Contact:** an attributed query log or capture/SNI shows that a TV contacted
  the hostname. Include sanitized timestamps and reproduction activity.
- **Purpose:** explain what identifies ads, telemetry or a functional service.
  DNS resolution and TLS identity identify infrastructure, not its purpose.
- **Compatibility:** record what happened when blocking the actual matching
  scope, including descendants for suffix rules.

For new SAFE admissions/promotions, require established ad/telemetry purpose
and a documented blocking test: model, exact firmware/webOS build, service
region, blocker/version and format, rule(s), exercised features, result and
date. Contact alone never promotes a sibling. Unknown details stay unknown.
The original G1 audit did not record its exact firmware build. Existing
exceptions are explicit: owner-directed `alphonso.tv` and three AU/UAE
`lgsmartad.com` exact-name extensions of the adopted dedicated-ad-zone
decision, not independent isolated smoke tests.

STRICT retains aggressive functional-risk and weak-evidence coverage.
For a new weak entry, supply attributed contact, attributed purpose evidence,
or an explicit linked sibling-coverage rationale. Do not import every resolving
twin automatically or infer its purpose from its name. Probe relevant
`eic`/`aic`/`kic`/`ruc` siblings and record candidates; resolution alone does
not require admission. A sibling of a non-weak entry does not inherit its
evidence. Issue #28 does not establish `ruc`'s geographic meaning.

Use `python3 scripts/verify.py --cross-check` for external **A-only** DoH
findings, avoiding your own filtering resolver. A second provider is attempted
only for non-LIVE findings. NO_A means NOERROR without an A record; neither it
nor NXDOMAIN proves retirement, descendant inactivity or compatibility.
`--fail-on-dead` exits nonzero for NXDOMAIN, not all inconclusive findings.
This network diagnostic is separate from structural `build.py check`.
Never automatically remove historical records based on DNS alone.

Regional reports need model, build, region and timestamps. New source-region
labels also require updating `SOURCE_REGION_LABELS` in `scripts/localize.py`;
that rewrite set is distinct from the optional `[REGION-SCOPED]` regex tag.
Current compatibility and format scope: [project overview](docs/overview.md).
Full evidence policy: [methodology](docs/methodology.md#from-data-to-tiers).
Network-wide STRICT rules for shared/third-party sites can affect non-TV clients.

## 2. Edit src/, never lists/

- `src/safe.txt` — lower-disruption ad/telemetry coverage, with scoped evidence and explicit exceptions; not a universal compatibility guarantee.
- `src/strict.txt` — the DELTA over safe (updates, ThinQ, LG Channels,
  weak-evidence entries). Do not repeat safe entries here.
- `src/zones.txt` — strict-only family apexes for whole-zone blocking in the
  adblock and dnsmasq formats.

Every line needs an inline annotation — format, tags, and examples in
[Annotated domains](#annotated-domains) below.

CI validates every PR that touches `src/` or `scripts/` — structural
violations (hostname, annotation, duplicate, overlap and regional-scope
constraints) fail the build; semantic truth and tier placement still need
evidence review. The generated `lists/`
directory is off-limits to PRs (CI rejects changes to it) — edit `src/`
instead.

## Format semantics

Use the canonical [format-scope table](docs/overview.md#format-scope) before
choosing a rule or testing compatibility. Domains/hosts are exact-name;
adblock/dnsmasq reach descendants, while optional regex generalizes only
explicitly tagged families and STRICT anchors. Current dnsmasq output uses
`address=/name/#`: null A (`0.0.0.0`) and AAAA (`::`) answers for the same
names and descendants, without membership changes. Hosts output remains
IPv4-only. Use a dnsmasq build accepting this syntax, as documented in the
[official manual](https://dnsmasq.org/docs/dnsmasq-man.html).
Older downloaded IPv4-only snippets need replacement and reload; run
`dnsmasq --test` on staged configuration before replacing live router
configuration. See the [installation procedure](docs/install.md#dnsmasq).
Dual-stack answers do not prevent IPv6 DNS-transport bypass or DoH;
the diagnostic scripts remain A-only.

Generated files have `#` metadata headers. AdGuard Home/uBlock Origin accept
those comments (`!` is canonical for custom adblock comments); dnsmasq reads
`#` header comments directly. STRICT anchors block only the apex in
domains/hosts, not its descendants. Source entries themselves never contain
wildcards.

## Annotated domains

The source of truth is annotated: `src/safe.txt`, `src/strict.txt`,
`src/zones.txt`. Annotations record attributed evidence and uncertainty, not
machine-verified truth. See the canonical [compatibility table](docs/overview.md#compatibility)
and run `python3 scripts/build.py inventory` for reproducible source counts
and anchor descriptions; counts are not independently tested service counts.

Every line needs an inline annotation:

    snu.lge.com # STRICT: firmware OTA check server

Line format: hostname, space, `#`, space, `TAG: nonempty description`.
The leading tag must match the source: `SAFE:`, `STRICT:` or `ZONE:`.
For example, `lge.com # ZONE: umbrella family — descendant scope in suffix formats`.
Write lowercase names without trailing dots or wildcards; the parser retains
lowercase/single-trailing-dot normalization for existing inputs.
Use `STRICT: weak ...` for explicitly weak evidence. `SAFE: weak ...` is
rejected (case-insensitive `weak` immediately after the tag); incidental prose
such as “weak signal” later in a description is not a classification.
Absence of `weak` does not establish independent compatibility testing.

One further tag is structural rather than evidential. `[REGION-SCOPED]`
anywhere in the annotation marks an entry whose family LG also serves behind
two-letter country prefixes (`de.lgeapi.com`, `br.lgeapi.com`, …):

    de.info.lgsmartad.com # SAFE: ad info endpoint [REGION-SCOPED]

It feeds the optional `lists/*-wildcard.txt` regex files and nothing else. The
eight shipped lists are byte-identical with every tag deleted, and a test asserts
exactly that. Rules:

- Tag only an entry that already carries its own evidence and annotation. The
  tag adds regional reach to a host that was audited; it never introduces a
  family, and no untagged hostname is ever generalised. Position in the
  annotation is free — entries can acquire trailing dated DNS notes without
  colliding with the tag.
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
- **Never list the bare `lgtvsdp.com` apex as an entry.** An apex address
  snapshot does not establish the status of descendants. The adblock output
  would emit `||lgtvsdp.com^`, covering every `<cc>.lgtvsdp.com` time host in
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
2. Edit `src/`, scripts or documentation, never generated `lists/`.
3. With Python 3.10+, run the applicable verification below.
4. Open the PR; CI regenerates lists after merge. Do not use automatic
   issue-closing keywords; leave issue closure and public follow-ups to the owner.

### Verification

Common structural/offline checks (all five Python suites):

```sh
python3 scripts/build.py check
python3 -m unittest discover -s scripts -p 'test_[bclnv]*.py'
```

For hook changes and applicable script CI:

```sh
python3 scripts/test_sync_clock.py
shellcheck -s sh examples/webos-hooks/*.sh
```

Changed dnsmasq output also needs real offline resolver A/AAAA proof, not
the A-only diagnostic. Install `dnsmasq` and `dig` (required; no silent skip),
then run separately from the stdlib unit tests:

```sh
python3 scripts/test_dnsmasq.py
```

No automated check establishes webOS feature compatibility.

When switching tiers, remove stale rules from the previous tier and refresh
the blocker. NextDNS imports are additive-only: re-importing SAFE does not
remove old STRICT entries; remove them manually. Detailed install/update/
rollback guidance: [install guide](docs/install.md).

## License

Content is CC BY 4.0, scripts MIT — see LICENSE and LICENSE-MIT.
