# AU and UAE domain reports

Classification rationale for [#22](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/22),
[#23](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/23), and
[#24](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/24).

## Evidence and tier decisions

- **#22 / #23:** @Merloko supplied DNS and TLS SNI observations from an Australian
  LG OLED65C2PSC, firmware 33.31.68, captured on 2026-10-28. Encrypted payloads
  do not establish service purpose. No live-block test was performed.
- **#24:** @kdeldycke supplied UniFi gateway observations from a UAE
  LG OLED77B46LA, webOS 25 10.3.2-33. They run STRICT with
  `ae.nextlgsdp.com` allowlisted for the clock. YouTube, Netflix and Universal
  Control work in that configuration after cold boot; that does not establish
  every endpoint's purpose or prove that the same setup works on other TVs.
- All 13 distinct reported hosts returned A records on both Google and
  Cloudflare DNS-over-HTTPS on 2026-11-10. DNS existence is not evidence of
  tracking, nor a substitute for a blocking test.

| Hosts | Tier | Reason |
|---|---|---|
| `au.ad.lgsmartad.com`, `au.info.lgsmartad.com`, `ae.info.lgsmartad.com` | SAFE | Observed endpoints in the existing dedicated ad zone. SAFE adblock/dnsmasq already cover them via `lgsmartad.com`; explicit entries fill the domains/hosts gap. |
| `au.nextlgsdp.com`, `ae.nextlgsdp.com` | STRICT | Shared SDP service with possible clock/store dependencies. The UAE reporter explicitly needs the latter open for time sync. Never generalise these hosts into a SAFE regex. |
| `au.rdx2.nextlgsdp.com`, `ae.rdx2.nextlgsdp.com` | STRICT, weak | Observed regional SDP hosts; cadence/contact alone does not prove telemetry. |
| `ae.lgeapi.com` | STRICT, weak | Same API family and unproven store/billing risks as `de.lgeapi.com`. |
| `ngfts.tv.wiselg.com`, `eic-gfts.tv.wiselg.com` | STRICT, weak | Observed file-transfer-family siblings, but payload purpose and isolated blocking impact are unknown. |
| `connect-client.lgthinq.com` | STRICT | ThinQ cloud endpoint; feature-affecting category, not SAFE telemetry. ThinQ impact was not tested. |
| `au.app.lgwebostv.com`, `au.elastic.lgwebostv.com` | STRICT, weak | Observed webOS endpoints with unknown function/app-store impact. Accept the family in the validator, but do not add an apex block or regional regex. |

The new `aic-gfts.tv.wiselg.com` and `kic-gfts.tv.wiselg.com` cluster twins also
returned A records on both DoH providers on 2026-11-10. They inherit the
observed `eic-` sibling's **weak STRICT** classification; neither was observed
in TV traffic. Existing `aic-`/`eic-`/`kic-ngfts.tv.wiselg.com` entries already
cover that cluster family.

All new `au.` / `ae.` entries participate in `scripts/localize.py`. The
localizer extrapolates names, not evidence: generated regional variants remain
explicitly unaudited. No zone anchors or wildcard rules were added.

## Clock and format caveats

STRICT adblock/dnsmasq already cover the reported `nextlgsdp.com`, `lgeapi.com`,
`wiselg.com`, and `lgthinq.com` descendants via zone anchors. Missing exact
names matter for domains/hosts consumers, not just substring searches of
`src/`. The `lgwebostv.com` hosts are genuinely new coverage in both formats.

For a clock dependency, allowlist the actual region host, e.g.
`@@||ae.nextlgsdp.com^` in AdGuard Home, rather than the entire SDP zone.
See the [clock FAQ](faq.md#homebrew-channel--https-apps-fail-after-power-loss-or-cold-boot).
The exact-name STRICT additions intentionally carry the same clock risk as
STRICT's existing whole-zone formats.

## Netflix report #21: diagnostics pending

[#21](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/21) has no TV
model, error code or blocked-domain log. It also does not establish whether
"strict" means this repository's list or UniFi's own CyberSecure content
filter. No speculative Netflix-related rule changes are justified.

Before proposing a fix, request:

1. TV model, webOS/firmware version and country/region.
2. Exact Netflix error or symptom, and whether launch, login or playback fails.
3. The imported list URL/format, or confirmation that only UniFi's built-in
   Strict setting is enabled; gateway/UniFi Network versions are useful too.
4. Whether Netflix works with just that specific list/filter disabled, keeping
   other filtering unchanged.
5. Timestamped blocked-domain logs for the TV around a failed launch. Redact
   local/public IPs, device identifiers and other private details as needed.

A clock/date check can follow if the error suggests TLS or time-sync failure.
Keep the issue open until the filter identity and a reproducible cause are
established. Each public reply requires the repository owner's individual
approval before posting.

## Upstream comparison #28

[#28](https://github.com/furkan-bayrak/lg-tv-blocklist/issues/28) compares this
project with Life's Good Without Spying 0.12.2. @kdeldycke reports an LG
OLED77B46LA (B4, UAE), webOS 25 `10.3.2-33`, but supplies no traffic capture or
per-host blocking test for these 86 names. Enabling categories together is not
an isolated compatibility test. No additions qualify for SAFE, including
Alphonso children: the owner-directed apex exception is not a blanket promotion.

**Disposition:** 79 names added to STRICT, seven deferred. `nsu.lge.com` and
`snu-dev.lge.com` have firmware-purpose evidence in the reporter's update-daemon
strings, not proof of live contact. The other 77 entries are tagged **weak**:
their purpose comes from upstream notes, not this project's device audit.
ThinQ, Home recommendations and Channels may break; shared third-party names
can also affect non-TV clients when filtering is network-wide. No new zone
anchors, regional regexes or SAFE entries are introduced.

All 79 additions returned A records on **both Google and Cloudflare DoH on
2026-11-17**. The following seven returned NOERROR but **no A, AAAA or CNAME
answer on either provider**; NOERROR alone does not mean a reachable endpoint.
They are not added, including as apex anchors:

| Deferred name | Upstream category |
|---|---|
| `thetake.com` | livepick / ACR shopping |
| `lgecloudapm.com` | Crash / APM |
| `eic-rum.elsa.lgecloudapm.com` | Crash / APM |
| `ibs.lgappstv.com` | SmartAd |
| `ibsstat.lgappstv.com` | SmartAd |
| `ibis.lgappstv.com` | SmartAd |
| `smartclip-services.com` | Third-party ads |

Source attribution: [Life's Good Without Spying at
`45fc13a`](https://github.com/lewisdoesstuff/lifesgoodwithoutspying/tree/45fc13a20eca0035694e1aec79acef9301cc294a/app/init/blocklist.d),
copyright 2026 Lewis Wood, MIT (notice retained in [LICENSE-MIT](../LICENSE-MIT)).
Category notes were consulted from `10-smartad.txt`, `20-acr.txt`,
`30-dashboard.txt`, `35-wiselg.txt`, `40-telemetry.txt`, `50-thinq.txt`,
`80-lgchannels.txt` and `90-updates.txt` at that immutable revision.

The 12 reported `ruc` names are included among the 79 live additions. Treat
`ruc` as another cluster prefix to check, not a two-letter country label;
its geographic meaning is not established here. `scripts/localize.py` therefore
leaves it untouched, as it does `aic`/`eic`/`kic`. The existing `us` country
label already handles `us.ibs.lgappstv.com`. The 517 country twins and 72
Content Store hosts explicitly excluded by the reporter remain outside this
change; their absence is not an endorsement to block them.
