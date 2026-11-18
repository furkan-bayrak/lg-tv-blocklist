# Project overview

LG TV Blocklist aims to reduce LG webOS advertising, ACR (Automatic Content Recognition) and telemetry traffic through DNS filtering. It is not a guarantee of silence, privacy or universal app compatibility.

## Project map

- [`src/`](../src/) contains annotated policy inputs: SAFE, the STRICT delta, and STRICT zone anchors. Edit these, not generated subscriptions.
- [`lists/`](../lists/) contains generated subscriptions and `SHA256SUMS`.
- [`scripts/`](../scripts/) contains the stdlib builder, source inventory, localizer and A-record diagnostics.
- [`examples/webos-hooks/`](../examples/webos-hooks/) contains optional rooted-TV DNS-egress and clock tools, with separate operational limitations.
- Historical [design](2026-09-09-lg-tv-blocklist-design.md) and [implementation plan](2026-09-09-lg-tv-blocklist-plan.md) are archival. Use this overview, the [contribution policy](../CONTRIBUTING.md), and the [install guide](install.md) for current behavior.

Run `python3 scripts/build.py inventory` from a checkout. It reports explicit
source names, explicitly weak annotations and STRICT anchors without any DNS
or device testing. Under **Effective matching scope**, the root count shows
how many listed suffixes have no broader listed parent. The covered-name
count shows how many other explicit names fall beneath those roots. The
report also shows STRICT-delta coverage by STRICT anchors and lists every
STRICT-delta name already covered by SAFE suffix rules, alongside its SAFE
parents.

Use these counts to understand adblock, dnsmasq and NextDNS matching, not
as a list of rules to remove. Domains/hosts still need explicit entries;
optional regex has its own tagged reach. None of these counts certify
evidence quality or compatibility.

## Choose a tier

**Start with SAFE** if retaining TV features matters. Its intended scope is established ad/telemetry services, not shared-service lockdown. It is not universally compatible: `alphonso.tv` remains an owner-directed exception without this project's independent blocking test. The AU/UAE `lgsmartad.com` additions are observed exact-name extensions of an existing dedicated-ad-zone decision, not isolated smoke tests.

**Choose STRICT deliberately** if you accept feature loss and uncertain collateral effects. It includes SAFE, feature-affecting services, weak/inferred candidates and nine zone anchors. OTA, ThinQ/voice cloud functions and LG Channels are intentional targets; store, streaming, clock and AirPlay dependencies can also be affected. Shared/third-party rules may affect non-TV clients when applied network-wide. STRICT does not ensure the TV stops all LG communication.

[Install by blocker](install.md), then check the actual TV's query path and features. When switching to SAFE, manually remove obsolete STRICT imports, regexes, hosts mappings and exceptions as appropriate. NextDNS imports are additive: rerunning the importer does not remove old entries.

## Three separate evidence questions

1. **Contact:** did an attributed TV query or connect to this name? Query logs and TLS SNI can establish contact, not purpose or harmlessness.
2. **Purpose:** what attributed evidence identifies its function? DNS/TLS identity identifies infrastructure, not tracking or TV contact.
3. **Compatibility:** what happened when the actual matching rule was blocked? Record model, exact firmware, region, blocker/format, rule scope, exercised features, result and date.

New SAFE admissions/promotions need established ad/telemetry purpose and that documented blocking test. Contact alone does not promote a sibling. Structural source validation cannot certify semantic truth. See the [evidence policy](methodology.md#from-data-to-tiers) and [contribution contract](../CONTRIBUTING.md).

## Compatibility

These are scoped observations and intended effects, not a certification of the current enlarged lists. The original German G1 audit predates later additions; its exact firmware build and feature-test dates were not recorded. Unknown metadata stays unknown. Issue references record evidence, not a claim that every report is resolved.

| Feature | Observed / intended outcome | Model, firmware, region, date | Evidence | Remaining uncertainty |
|---|---|---|---|---|
| Streaming | Netflix, Prime, HBO and YouTube worked in the historical G1 app smoke test. SAFE intends to preserve them; current STRICT is not guaranteed to. | G1, exact build unknown, Germany; exact smoke-test date unknown | [Audit](methodology.md#from-data-to-tiers) | Not a test of today's enlarged lists or other apps/models. [#21](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/21) (2026-11-09) reports Netflix failure with UniFi CyberSecure “strict”; TV/build/region and whether this repository's list was used remain unknown, cause unresolved. |
| Store / app installation and updates | Worked in the historical G1 smoke test. STRICT can break shared store services. A C3 reporter says removing `eic.tv.wiselg.com` restored store/app updates; that host is now STRICT, not SAFE. | G1 metadata as above; OLED65C34LA, webOS 26 `11.2.0-3711`, region unknown, reported 2026-11-10 | [Audit](methodology.md#from-data-to-tiers), [#25](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/25), [narrow carve-out recipe](faq.md#i-want-strict-but-keep-the-lg-content-store) | #25 does not establish compatibility of every current SAFE rule; exact list revision/format and region were not supplied. Recipe is a diagnostic starting point, not a verified universal allowlist. |
| Firmware OTA | SAFE intends to preserve OTA; STRICT intentionally blocks firmware/update families. | Original G1 audit; exact build/test date unknown, Germany | [Audit and firmware-diff recipe](methodology.md#firmware-diff-whats-new-in-this-update) | No current cross-model update test; source purpose evidence is not an update success/failure test. |
| ThinQ / voice cloud functions | SAFE intends to preserve shared functional services; STRICT deliberately targets ThinQ cloud communication and may impair voice/cloud features. | No isolated compatibility test metadata recorded | [Regional purpose/uncertainty notes](regional-reports.md#evidence-and-tier-decisions), [STRICT annotations](../src/strict.txt) | Endpoint purpose and feature impact differ; no blanket test of voice assistants or every ThinQ function. |
| LG Channels | Intentional STRICT target; SAFE does not intend to disable it. | No isolated compatibility test metadata recorded | [STRICT annotations](../src/strict.txt) | No current per-model Channels compatibility test. |
| Clock / cold-boot HTTPS | Rooted G1 clock reset to 2021 after power loss, breaking TLS. A UAE B4 report needed `ae.nextlgsdp.com` open for time sync; later #29 used NTP with it blocked. STRICT's SDP scope retains clock risk. | G1: Germany, exact build/date unknown; B4 OLED77B46LA, webOS 25 `10.3.2-33`, UAE; reports November 2026 | [Clock recipe](faq.md#homebrew-channel--https-apps-fail-after-power-loss-or-cold-boot), [regional notes](regional-reports.md#clock-and-format-caveats), [#29](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/29) | Allow only the host actually needed; other filters and cached answers matter. A clock workaround does not establish DNS or AirPlay compatibility. |
| AirPlay | First pairing failed with STRICT and SDP blocked on the UAE B4 despite correct time. A rooted skip-check workaround restored cold-boot/standby pairing. Upstream reproduced failure/workaround on a G4. | B4 OLED77B46LA, webOS 25 `10.3.2-33`, UAE; log 2026-11-13, report 2026-11-17. Upstream G4, webOS 9.2.4; region and exact test date unknown | [#29 and upstream evidence](regional-reports.md#airplay-report-29), [diagnostic options](faq.md#airplay-says-unable-to-connect-after-the-pairing-code) | Allowlisting the regional host is **untested** as an AirPlay fix. SAFE AirPlay is not independently tested; no demonstrated DE/CA failure. A rooted credential-check workaround is not a DNS-list fix. |

## Format scope

Choose matching semantics, not just a filename. Wider coverage can create wider breakage.

| Format / destination | Matching scope | Important limit |
|---|---|---|
| `*-domains.txt` | Exact names | A zone anchor blocks only that apex, not descendants, under exact-name consumption. |
| `*-hosts.txt` | Exact names, `0.0.0.0` IPv4 mapping | No wildcard or generated IPv6 mapping; TV daemons may bypass hosts resolution. Use generated files, not the annotated STRICT delta. |
| `*-adblock.txt` | `||name^` matches name and descendants | Includes descendants never enumerated or observed. |
| `*-dnsmasq.txt` | `address=/name/#` matches name and descendants; null A (`0.0.0.0`) and AAAA (`::`) answers | Same hostname membership and descendant scope as before. Requires a build accepting this syntax; dual-stack answers do not prevent IPv6 DNS-transport bypass or DoH. |
| Optional `*-wildcard.txt` regex | Two-letter variants of explicitly `[REGION-SCOPED]` families; STRICT also includes the nine anchors | Not all country-looking names or all LG families. Paste as regex rules, not ordinary adlists; supplements rather than replaces a subscription. |
| NextDNS denylist imports | Each name and descendants | No regex/custom list subscription; additive importer never prunes. Exact-name input does not produce exact-name enforcement here. |

SAFE adblock/dnsmasq already cover descendants of listed apexes such as `lgsmartad.com`; regex is not required to cover country names beneath those apexes. Neither tier covers every possible regional endpoint. [Regional troubleshooting](faq.md#im-not-in-germany--do-the-lists-still-work-for-me) explains localization and explicitly unaudited extrapolation.

Older downloaded dnsmasq snippets using `address=/name/0.0.0.0` retain their
IPv4 limitation. Replace and reload them following the
[install procedure](install.md#dnsmasq), including `dnsmasq --test` before
replacing live router configuration. The
[official manual](https://dnsmasq.org/docs/dnsmasq-man.html) documents the
`#` null-address syntax; use a build that accepts it. Closing the AAAA gap
can block features that previously escaped; no TV compatibility result is
implied.

## What diagnostics do not prove

[`check_blocking.py`](../scripts/check_blocking.py) checks A-record answers at a selected resolver, not AAAA filtering, TV routing or TV caches. [`verify.py`](../scripts/verify.py) checks external A answers; `--cross-check` attempts a second provider only for non-LIVE findings. NO_A is NOERROR without an A record, not proof of delegation or retirement. DNS snapshots and TLS certificates do not prove service purpose or feature compatibility.

DNS filtering cannot stop IP-literal traffic, DoH or queries bypassing the chosen resolver. The optional rooted hook redirects IPv4 port 53 and drops supported port-853 traffic; unsupported IPv6, DoH and stale DNAT targets remain limitations. See [the two caveats](../README.md#the-two-caveats), [hook limitations](../examples/webos-hooks/README.md#caveats) and the [independently resolvable-canary procedure](install.md#is-it-actually-blocking).
