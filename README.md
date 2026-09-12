# LG TV Blocklist

An evidence-annotated DNS blocklist for LG webOS TV telemetry — the data your TV sends home about what you watch and do — plus ads and phone-home traffic. It is for LG TV owners who run a DNS blocker (Pi-hole, AdGuard Home, NextDNS) and want the TV to stop reporting home without breaking the apps they use.

Not affiliated with LG Electronics. LG is a trademark of LG Corp.

## Why trust this list

Built by watching a real LG G1's network traffic and DNS logs, cross-checked against public reports. Every entry notes what it blocks and the evidence behind it — observation, not speculation. Method and replication steps: [docs/methodology.md](docs/methodology.md).

## Which list should I use?

| | SAFE | STRICT |
|---|---|---|
| **Blocks** | Telemetry, ads, and ACR (Automatic Content Recognition — the TV's "what are you watching" reporting) | Everything in SAFE, plus firmware OTA (over-the-air) updates, ThinQ cloud sync, and LG Channels |
| **For** | Almost everyone | Privacy-focused users who want the TV to fully stop talking to LG |
| **Cost** | Streaming apps, Content Store, and app updates keep working (verified on an LG G1) | Those services stop working on purpose |

**What breaks in STRICT (read this):**

| Feature | SAFE | STRICT |
|---|---|---|
| Netflix / Prime / HBO / YouTube | works | works |
| LG Content Store | works | may degrade ([carve-out recipe](docs/faq.md#i-want-strict-but-keep-the-lg-content-store)) |
| Firmware OTA updates | works | blocked |
| ThinQ app / voice assistant cloud sync | works | blocked |
| LG Channels | works | blocked |
| LG account login | works | may fail |

## Install

Pick a tier above, then load the matching file into your blocker:

| Your blocker | SAFE | STRICT |
|---|---|---|
| Pi-hole, NextDNS, Unbound | [safe-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt) | [strict-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt) |
| AdGuard Home, uBlock Origin | [safe-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt) | [strict-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt) |
| Rooted TV `/etc/hosts` | [safe-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-hosts.txt) | [strict-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-hosts.txt) |

Checksums: [SHA256SUMS](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/SHA256SUMS). Not in Germany? The exact-name lists only cover the regions present — see the [region FAQ](docs/faq.md#im-not-in-germany--do-the-lists-still-work-for-me) and `scripts/localize.py`.

**Rooted TV (webosbrew / Homebrew Channel):** mirror the `-hosts.txt` entries into `/etc/hosts`; a webosbrew `init.d` hook (a boot-time script) can rewrite that file at every boot (it lives in RAM and resets on reboot — mechanism: [webosbrew filesystem-overlays](https://www.webosbrew.org/pages/filesystem-overlays)). Mirror `src/safe.txt`, or `src/strict.txt` for the full lockdown. Separately, [`examples/webos-hooks/`](examples/webos-hooks/) ships a boot hook that forces all TV DNS through your resolver and drops encrypted DNS (DoT/DoQ, port 853) — the fix for the hardcoded-resolver bypass in [caveat 1](#the-two-caveats). Rollback and caveats: [hook README](examples/webos-hooks/README.md).

## The two caveats

1. **LG hardcodes public resolvers.** webOS daemons have been observed using `8.8.8.8` / `1.1.1.1` directly, and can use encrypted DNS, so a DNS blocklist alone is not a guarantee. Redirect outbound port 53 to your resolver and block port 853 at your firewall; on a rooted TV the [DNS-egress hook](examples/webos-hooks/) does it on-device. A hosts file alone is not enough either — some daemons ignore it and query the TV's built-in DNS resolver directly.
2. **Exact names, not wildcards.** Entries name specific hosts, so whole-family coverage depends on enumeration. If your TV talks to an LG domain that is not on the list, [open a new-domain issue](https://github.com/furkan-bayrak/lg-tv-blocklist/issues) — that is exactly how the list grows.

## FAQ

- **Which tier should I use?** SAFE for almost everyone; STRICT if you want the TV to fully stop talking to LG.
- **Will this break Netflix / Prime / HBO / YouTube?** No — verified on an LG G1.
- **My TV ignores my Pi-hole / AdGuard. Why?** webOS has a built-in DNS resolver and hardcoded fallback DNS; fix it at the router, or use the rooted hook.
- **I'm not in Germany — do the lists work?** STRICT's adblock list is region-complete; the exact-name lists can be adapted with `scripts/localize.py --region <cc>`.
- **I want STRICT but keep the LG Content Store.** See the [carve-out recipe](docs/faq.md#i-want-strict-but-keep-the-lg-content-store).
- **Why doesn't SAFE block all of `lge.com`?** That would kill the Content Store, updates, and account login along with the telemetry.

Full list: [docs/faq.md](docs/faq.md).

## Dig deeper

- **Methodology** — how the data was collected and how to replicate it, including a firmware-diff recipe: [docs/methodology.md](docs/methodology.md).
- **Upstream tracker** — where these domains were submitted to community blocklists: [docs/upstream.md](docs/upstream.md).
- **Source of truth** — annotated lists: [src/safe.txt](src/safe.txt), [src/strict.txt](src/strict.txt), [src/zones.txt](src/zones.txt). The comments tell you what every entry does and the evidence behind it, e.g. `snu.lge.com # STRICT: firmware OTA check server`.
- **Contributing** — evidence rules and how to add a domain, edit `src/` only (CI regenerates the lists): [CONTRIBUTING.md](CONTRIBUTING.md) (templates: [new domain](.github/ISSUE_TEMPLATE/01_new_domain.md), [breakage](.github/ISSUE_TEMPLATE/02_breakage.md)).
- **Join as a maintainer** — LG runs dozens of webOS versions and regional endpoints; captures or query logs from a C-series, G-series, or other model are exactly what this needs. [Open an issue](https://github.com/furkan-bayrak/lg-tv-blocklist/issues) or submit a PR.

## License

Content and generated lists: [CC BY 4.0](LICENSE). Scripts and workflows: [MIT](LICENSE-MIT).
