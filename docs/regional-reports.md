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
