# LG TV Blocklist — Design Spec

Date: 2026-09-09. Status: approved for planning.
Origin: two-week empirical audit of an LG G1 (webOS) TV — root access, service kills, iptables, 44.8k-packet capture, 267k-query AdGuard log analysis. Authored from audit data; not scraped from other lists.

## 1. Goal

A small, curated, evidence-based DNS blocklist for LG TV / webOS telemetry, published as an open GitHub repository that the community can extend. Inspired by HaGeZi's dns-blocklists quality bar (tiered lists, generated artifacts, annotated, checksummed) but scoped to LG only.

Non-goals (YAGNI): non-LG devices; LG TVs' *advertising* outside webOS; auto-probe bots; release assets; wildcard/dnsmasq/unbound/more formats; model-specific hardware lists.

## 2. Audience & constraints

- Primary users: Pi-hole, AdGuard Home, NextDNS, /etc/hosts (rooted webOS), any exact-name DNS list consumer.
- SAFE tier promise: stock-TV-safe — Content Store, app updates, app logins, Netflix/Prime/HBO/YouTube continue to work.
- STRICT tier: rooted/privacy-max users — zero LG communication; OTA updates and ThinQ/LG Channels break **by design** and are documented.

## 3. Content model

### 3.1 Tiers and source files

- `src/safe.txt` — proven telemetry/ad/ACR hostnames only. Subdomain-level. Nothing with update/store/ThinQ/feature function.
- `src/strict.txt` — **DELTA ONLY** (the extra domains over safe). Decision locked: strict is compiled as `safe ∪ strict-delta`. Contributors adding a safe telemetry domain edit only `safe.txt`; the strict outputs inherit it automatically. Full-standalone strict.txt with a superset CI check was considered and rejected (double bookkeeping, drift risk).
- `src/zones.txt` — optional STRICT-only zone anchors: family apexes for whole-zone blocking in the adblock format (e.g. `lge.com`). Only present where we have not enumerated (and don't intend to enumerate) the full family. Semantics differ by format — documented in README and enforced by `zones.txt` never being merged into `safe`.

### 3.2 Annotation & evidence rules (contribution contract)

Every source line must carry an inline comment after `#`:
`domain.example # <tier-tag>: <function> — <evidence>`

- Function: one line, what LG uses it for (firmware OTA, telemetry beacon, ads, ACR, ThinQ sync, LG Channels, update CDN, unknown).
- Evidence: empirical basis — "seen in boot burst", "blocked live, Netflix/Prime/HBO/YouTube verified", "querylog 6-min heartbeat", "capture SNI", or issue-report reference.
- Evidence strength must be honest: entries with weak evidence are tagged `weak` and default to STRICT (never risk the SAFE promise on a guess).
- Duplicates within a file, duplicates across `safe.txt`/`strict.txt`, malformed hostnames, and non-LG-related domains fail CI.

### 3.3 Seed content (from the G1 audit)

Compiled from the audit's 47-name hosts file plus the 15-family AdGuard rule set and querylog evidence. Every entry below is one source line (comments summarized). Evidence solid = observed multiple times / function known / streaming apps verified while blocked.

SAFE — telemetry / ads / promo (streamers verified unaffected):

| Domain | Function / evidence |
|---|---|
| cdpbeacon.lgtvcommon.com | ACR/telemetry beacon (heartbeat) |
| ads.lgtvcommon.com | ad delivery |
| homeprv.lgtvcommon.com | home-screen provisioning/promos |
| eic.nudge.lgtvcommon.com | nudge/notification telemetry |
| recommend.lgtvcommon.com | recommendations/promos |
| eic.wiseconfig.lgtvcommon.com | cloud config telemetry (6-min heartbeat pattern) |
| eic.lgtviot.com | IoT telemetry (top query family, 5.1k queries) |
| eic.api.lgtviot.com | IoT telemetry API |
| eic.tv.wiselg.com | TV telemetry |
| de.nextlgsdp.com | SDP region endpoint (telemetry) |
| lgsmartad.com | ad zone apex (dedicated ad family) |
| de.info.lgsmartad.com | ad info |
| de.emp.lgsmartplatform.com | smart-platform telemetry |
| smart.adtvc.app | ad/video ads |
| adsdtvc.com | ad zone |
| ad.lgappstv.com | ad delivery on store CDN family |
| us.lgtvsdp.com | SDP telemetry (region) |
| lgtvsdp.com | SDP telemetry apex |
| initscr.lge.com | initial-setup telemetry (boot) |

STRICT delta — updates, feature-killers, weak-evidence (default strict):

| Domain | Function / evidence |
|---|---|
| snu.lge.com | firmware OTA check |
| su.lge.com / su-dev.lge.com / su-ssl.lge.com | OTA update servers |
| ngfts.lge.com / gfts.lge.com / eic-ngfts.lge.com / eic-gfts.lge.com | update/content file transfer |
| ngfts.nextlgsdp.com | update transfer on SDP |
| eic-ngfts.tv.wiselg.com | update transfer (wiselg) |
| lss.lgthinq.com / eic-op-lss.lgthinq.com | ThinQ cloud sync / voice-assistant backend |
| bss.lgechannel.com / lgechannel.com | LG Channels (FAST) backend + apex |
| lgtvonline.lge.com | unknown (weak) — post-boot only |
| am.lge.com / ig.lge.com | unknown (weak) — observed, store-independent assumed only |
| a.lgappstv.com / lgappstv.com | store-CDN-adjacent (weak: app-update function unproven either way) |
| fms.lgunifiedsmart.com | smart-family messaging (weak) |
| de.lgeapi.com | region API (weak: store/billing interplay unproven) |
| de.ibs.nextlgsdp.com | possible in-app billing on SDP (weak — store risk) |
| eic-ocp.lgtviot.com | unknown (weak — NOT the panel-compensation daemon; DNS only) |
| eic.cdplauncher.lgtvcommon.com | content-launcher CDP (weak) |
| eic.lgchhomeapp.lgtvcommon.com | home-app service (weak) |
| rdx2.lgtvsdp.com | unknown (weak) |

ZONES (strict-only, adblock `||zone^` semantics; apex-only in hosts/domains formats): `lge.com`, `lgeapi.com`, `wiselg.com`, `lgthinq.com`, `lgtviot.com`, `nextlgsdp.com`, `lgunifiedsmart.com`.

## 4. Repository layout

```
lg-tv-blocklist/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── 01_new_domain.md        # evidence fields: querylog/pcap snippet, device, tier request
│   │   └── 02_breakage.md          # app, symptom, tier, revert-window question
│   └── workflows/
│       └── build.yml
├── docs/
│   └── 2026-09-09-lg-tv-blocklist-design.md   # this spec
├── scripts/
│   ├── build.py                     # stdlib only
│   └── (test_build.py lives here or tests/)
├── src/
│   ├── safe.txt
│   ├── strict.txt                   # delta only
│   └── zones.txt
├── lists/                           # generated; not edited by hand
│   ├── safe-domains.txt / safe-hosts.txt / safe-adblock.txt
│   ├── strict-domains.txt / strict-hosts.txt / strict-adblock.txt
│   └── SHA256SUMS
├── CONTRIBUTING.md
├── LICENSE                          # CC BY 4.0 (content + docs)
├── LICENSE-MIT                      # scripts
└── README.md
```

## 5. Build script spec (`scripts/build.py`)

Pure stdlib (argparse, hashlib, ipaddress not needed, re, datetime, pathlib, unittest).

- Input: `src/safe.txt`, `src/strict.txt`, `src/zones.txt`.
- Parse: strip full-line comments and inline `# comment`; lowercase; validate hostname regex (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$`, ≤253 chars, no leading/trailing dot).
- Validate:
  - duplicates within a file → fail
  - any strict/zones entry present in safe → fail (tells contributor "dupe — safe already covers it")
  - strict.txt and zones.txt overlap → warn + dedupe (strict wins)
- Compile:
  - safe = safe.txt sorted
  - strict = sorted(set(safe + strict.txt)); zones appended **only to adblock output** as `||zone^` and to domain/host outputs as apex lines — semantic difference documented in headers.
- Emit per tier (tiers `safe`, `strict`): `{tier}-domains.txt` (plain, one per line), `{tier}-hosts.txt` (`0.0.0.0 {d}`), `{tier}-adblock.txt` (`||{d}^`). Header on every file: title, tier, generated timestamp, entry count, source URL (raw GitHub), maintenance note.
- `SHA256SUMS` over the six generated files.
- Modes: `build` (write lists/), `check` (parse + validate + dry-run compile in memory; exit 1 on any content error; no filesystem writes — used by CI on PRs and after merge), `test` (run bundled unittest suite).

Determinism: sorted input and a fixed header format. Header timestamp = generation time (injected on `build` only). `check` compiles fully in memory and never diffs against committed `lists/` artifacts — so a per-build header timestamp can never cause a false CI failure (timestamp pitfall avoided by construction). Generated files are committed only when the merge job actually runs (src/scripts changed), so per-build timestamps cause zero churn on identical source.

## 6. CI/CD (`.github/workflows/build.yml`)

- Triggers: `pull_request` (paths src/scripts), `push` to main (paths src/scripts), `workflow_dispatch`.
- PR job: `python scripts/build.py check` on PR head + `python -m unittest` — contributors never touch `lists/`; the merge job regenerates.
- Main job: `python scripts/build.py`, then commit-and-push `lists/` only when the diff is non-empty with `github-actions[bot]` identity and `[skip ci]` in the message. `concurrency: { group: lists, cancel-in-progress: false }` guards against overlapping runs. No secrets anywhere.
- No secrets used anywhere.

## 7. README / docs outline

1. What this is, why it exists, evidence bar (audit provenance).
2. Raw install links per tier × format (raw.githubusercontent.com) + one-line usage per platform: Pi-hole (Adlists URL → either plain-domains or adblock URL), AdGuard Home (custom filter URL → adblock URL), NextDNS (plain-domains URL), /etc/hosts / rooted webOS (hosts URL, note the webosbrew hook approach as advanced section).
3. Tier table: what breaks in STRICT (OTA, ThinQ, LG Channels) — "know what you're turning off."
4. Format-semantics note: hosts/domains = exact-name; adblock = `||domain^` subdomain matching; zone anchors behave differently across formats (link to FAQ).
5. Hard-won caveats from the audit: LG hardcodes public resolvers (8.8.8.8/1.1.1.1) — block outbound 53/853/DoH at the router or hosts-file locally; hosts-file is the only thing that stops hardcoded-DNS daemons on the TV itself.
6. FAQ: "Will this break Netflix?", "What about LG Channels?", "Why no `*.lge.com` whole-zone in safe?"
7. Maintainers + license + contribution pointer.

## 8. Contribution model

- Issues: the two templates above (evidence-first).
- PRs: edit `src/*.txt` only (never `lists/`). CI enforces validity + no drift. Maintainer (user) merges after evidence review; community members with repeated quality contributions may be invited.
- Contribution guide (`CONTRIBUTING.md`) documents the evidence bar: "no capture, no merge" for unknown domains; known-function domains accepted with a credible reference + device/webOS version.

## 9. License

- Content (src, lists, README, docs): CC BY 4.0 (user decision; final answer, supersedes earlier BY-NC pick).
- Scripts (scripts/, .github/): MIT.
- Both texts included verbatim. Header comment in generated files notes the CC BY 4.0 content license.

## 10. Local mirror & first release

- Local working copy: `C:\Users\furka\projects\lg-tv-blocklist` (git repo already initialized, branch `main`).
- Seed content derived from audit mirrors in `C:\wezterm_temp\opencode\lg-rollback\` (00-block-lg-hosts.sh DOMAINS + agh_lg.py RULES + runbook evidence).
- Repository created on user's GitHub account (name `lg-tv-blocklist`; username/org requested at creation time). Public.
- First commit: spec + scaffold + seed + generated lists + docs, single coherent commit or small logical commits (scaffold → content → build → CI → docs).

## 11. Open questions (tracked, not blocking)

- GitHub username/org + display identity for commits.
- Whether LG *soundbar/monitor* owners (webOS siblings) are in scope later — no now.
- Zone anchor list final wording (which zones, whether `lgtvsdp.com` and `lgsmartad.com` deserve zone status in strict beyond the enumerated apex) — resolved during seeding review with user.
