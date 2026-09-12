# Upstream Submissions

Outcome tracker for audited SAFE-tier hostnames submitted from [furkan-bayrak/lg-tv-blocklist](https://github.com/furkan-bayrak/lg-tv-blocklist) to upstream DNS blocklist projects (per-domain evidence and methodology in-repo). README "upstreamed" claims are added only after a merge.

| Date | Project | Link | Domains | Status | Notes |
|---|---|---|---|---|---|
| 2026-09-11 | Perflyst/PiHoleBlocklist | [PR #170](https://github.com/Perflyst/PiHoleBlocklist/pull/170) | `de.emp.lgsmartplatform.com`, `de.info.lgsmartad.com`, `eic.api.lgtviot.com`, `eic.lgtviot.com`, `eic.nudge.lgtvcommon.com`, `eic.tv.wiselg.com`, `eic.wiseconfig.lgtvcommon.com`, `lgsmartad.com`, `lgtvsdp.com` | open | Originally 16 domains; trimmed pre-review to 9 live-verified (7 NXDOMAIN dropped). `lgtvsdp.com` = delegated apex, SOA-only. Version header untouched (offered in PR body). Branch `add-lg-webos-audited-domains`; commits `8eb516b` + `2a91299`. |
| 2026-09-11 | hagezi/dns-blocklists | [issue #11432](https://github.com/hagezi/dns-blocklists/issues/11432) | `ad.lgappstv.com`, `adsdtvc.com`, `smart.adtvc.app` | closed — not accepted (NXDOMAIN/dead; "dead domains are not added" policy) | Verified on public resolvers (1.1.1.1/8.8.8.8); close-out comment posted. hagezi's new umbrellas (`lgtvcommon.com`, `lgsmartad.com`, `nextlgsdp.com`, `alphonso.tv`, `lgads.tv`) already cover 8 audited hostnames — hagezi track complete, nothing live and in-scope remains. |

2026-09-12 recheck: all 7 NXDOMAIN-trimmed [PR #170](https://github.com/Perflyst/PiHoleBlocklist/pull/170) candidates remain NXDOMAIN (checked via 1.1.1.1); U3 capture pass found 0 new live LG hostnames.
