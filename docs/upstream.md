# Historical upstream submissions

This records the 2026-09-11/12 submission snapshot, not current SAFE
endorsements or live upstream PR status. Consult the linked projects for
current status. `eic.tv.wiselg.com` is now STRICT after issue #25;
`lgtvsdp.com` is now forbidden as a source apex because suffix formats would
block regional time hosts. Its SOA-only response was not an address-live result.
Current policy and scope: [overview](overview.md), [methodology](methodology.md).

| Date | Project | Link | Domains | Status | Notes |
|---|---|---|---|---|---|
| 2026-09-11 | Perflyst/PiHoleBlocklist | [PR #170](https://github.com/Perflyst/PiHoleBlocklist/pull/170) | `de.emp.lgsmartplatform.com`, `de.info.lgsmartad.com`, `eic.api.lgtviot.com`, `eic.lgtviot.com`, `eic.nudge.lgtvcommon.com`, `eic.tv.wiselg.com`, `eic.wiseconfig.lgtvcommon.com`, `lgsmartad.com`, `lgtvsdp.com` | open at snapshot; current status not checked | Originally 16 candidates; seven NXDOMAIN candidates removed before review. Eight address-resolving candidates plus SOA-only `lgtvsdp.com`, not nine address-live names. Version header untouched; branch `add-lg-webos-audited-domains`, commits `8eb516b` + `2a91299`. Current tier/apex decisions differ as noted above. |
| 2026-09-11 | hagezi/dns-blocklists | [issue #11432](https://github.com/hagezi/dns-blocklists/issues/11432) | `ad.lgappstv.com`, `adsdtvc.com`, `smart.adtvc.app` | closed/not accepted at snapshot under NXDOMAIN policy | Snapshot recorded public-resolver checks and a close-out comment. Upstream umbrellas then covered eight audited names; this is not a claim about current reachability, status or compatibility. |

2026-09-12 recheck: all 7 NXDOMAIN-trimmed [PR #170](https://github.com/Perflyst/PiHoleBlocklist/pull/170) candidates remain NXDOMAIN (checked via 1.1.1.1); a capture pass (AdGuard querylog, rooted G1) found 0 new live LG hostnames.
