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

**Regional query logs welcome:** include the region, timestamp, and client
(TV model/name). Region-prefixed entries (`de.`, `us.`) can be extended with
evidence from your region — regional coverage is the main gap in this list.
New region prefixes must also be added to `SOURCE_REGION_LABELS` in
`scripts/localize.py`; otherwise `localize.py` silently leaves those entries
untouched.

## 2. Edit src/, never lists/

- `src/safe.txt` — telemetry/ad hostnames that are safe for stock TVs.
- `src/strict.txt` — the DELTA over safe (updates, ThinQ, LG Channels,
  weak-evidence entries). Do not repeat safe entries here.
- `src/zones.txt` — strict-only family apexes for whole-zone blocking in the
  adblock format.

Every line needs an inline annotation:

    snu.lge.com # STRICT: firmware OTA check server

Line format: hostname, space, `#`, space, `TAG: short description`. The
description names the function; entries with hard evidence add it after an
em-dash (`cdpbeacon.lgtvcommon.com # SAFE: ... (6-min heartbeat pattern
observed)`). Tags: `SAFE`, `STRICT`, `ZONE`. Lowercase only, no trailing
dot, no wildcards — this list is exact-name (see README "Format
semantics"). Weak-evidence entries are tagged `weak` and belong in
strict.txt by policy.

CI validates every PR that touches `src/` or `scripts/` — structural
violations (malformed, duplicate, or non-LG hostnames) fail the build;
semantic tier placement is reviewed by maintainers. The generated `lists/`
directory is off-limits to PRs (CI rejects changes to it) — edit `src/`
instead.

## Workflow

1. Fork, branch off `main`.
2. Edit one or more files under `src/`.
3. Run `python3 scripts/build.py check && python3 scripts/test_build.py` locally.
4. Open the PR. The merge job regenerates `lists/` automatically — never
   commit generated files yourself.

## License

Content is CC BY 4.0, scripts MIT — see LICENSE and LICENSE-MIT.
