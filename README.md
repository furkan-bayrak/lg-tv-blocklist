# LG TV Blocklist

Curated, evidence-based DNS blocklist for LG webOS TV telemetry, ads, and
phone-home traffic. Born from a two-week root-level audit of an LG G1:
44,800-packet captures, 267,000-query DNS logs, per-service investigation.
Every entry carries an annotation explaining what it blocks and the evidence.

Not affiliated with LG Electronics. LG is a trademark of LG Corp.

## Lists

> **Quick Summary:**
> * **Just want to stop ads, ACR, and telemetry without breaking your TV?** Use **SAFE**. Netflix, Disney+, Prime, and the LG App Store keep working normally.
> * **Want the TV to fully shut up — no firmware updates, no ThinQ cloud sync, no LG Channels?** Use **STRICT**. Those services are blocked on purpose — expect them to stop working.

Questions? See the [FAQ](docs/faq.md) — tier choice, keeping the Content Store on STRICT, and resolver troubleshooting.

| List | Domains (Pi-hole/NextDNS) | Hosts (/etc/hosts) | AdBlock (AdGuard Home/uBO) |
|---|---|---|---|
| **SAFE** — blocks telemetry/ads/ACR; store, app updates, Netflix/Prime/HBO/YouTube keep working | [safe-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt) | [safe-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-hosts.txt) | [safe-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt) |
| **STRICT** — everything in SAFE plus OTA updates, ThinQ cloud, LG Channels. Rooted/privacy-max users only. **Things break on purpose.** | [strict-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt) | [strict-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-hosts.txt) | [strict-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt) |

Checksums: [SHA256SUMS](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/SHA256SUMS)

## Install

**Pi-hole** (v5/v6): Adlists → Add — paste the `-domains.txt` URL of your
tier, then `pihole -g`.

**AdGuard Home**: Filters → DNS blocklists → Add blocklist — paste the
`-adblock.txt` URL.

**NextDNS / Unbound / Technitium**: import the `-domains.txt` URL.

**Rooted webOS**: use the `-hosts.txt` entries in `/etc/hosts`. Advanced:
webosbrew init.d hook that rewrites the (tmpfs) hosts file at every boot —
see [docs](https://www.webosbrew.org/pages/filesystem-overlays) for the init.d
mechanism; the domain set to mirror is `safe.txt` (or `strict.txt` for the
full lockdown).

## What breaks in STRICT (read this)

| Feature | SAFE | STRICT |
|---|---|---|
| Netflix / Prime / HBO / YouTube | works | works |
| LG Content Store | works | may degrade ([carve-out recipe](docs/faq.md#i-want-strict-but-keep-the-lg-content-store)) |
| Firmware OTA updates | works | blocked |
| ThinQ app / voice assistant cloud sync | works | blocked |
| LG Channels | works | blocked |
| LG account login | works | may fail |

## Format semantics

- `-domains.txt` / `-hosts.txt`: **exact-name** — `snu.lge.com` blocks that
  host only, not the whole zone.
- `-adblock.txt`: `||snu.lge.com^` also matches subdomains of that name.
- STRICT zone anchors (see `src/zones.txt`) only achieve whole-zone blocking
  in the adblock format; in domains/hosts they block the apex domain.

## The two caveats every LG owner should know

1. **LG hardcodes public resolvers.** webOS daemons have been observed using
   8.8.8.8 / 1.1.1.1 directly, bypassing your router's DNS entirely. A DNS
   blocklist alone is not a guarantee: block/redirect outbound port 53 and
   853 (DoT) at the firewall for the TV. A hosts file on a rooted TV only
   helps NSS-based lookups — daemons that query the local stub directly
   still escape it.
2. **Exact-name vs wildcard.** Because we curate subdomain-level entries,
   whole-family coverage depends on enumeration. If your TV shows traffic to
   an LG domain not on the list, open a `new-domain` issue — that's exactly
   how the list grows.

## Annotated domains

The source of truth is annotated: `src/safe.txt`, `src/strict.txt`,
`src/zones.txt`. Reading the comments there tells you what every entry does
and the evidence behind it. The tier table above summarizes the trade-offs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — evidence required, edit `src/`
only, CI does the rest. Issue templates: [new domain](.github/ISSUE_TEMPLATE/01_new_domain.md) /
[breakage](.github/ISSUE_TEMPLATE/02_breakage.md).

- **Methodology** — how the data was collected and how to replicate it (including a firmware-diff recipe): [`docs/methodology.md`](docs/methodology.md)

## Join as a Maintainer / Contributor

I built this from empirical packet captures and query logs on an LG G1, but
LG maintains dozens of webOS versions and regional endpoints. If you have
captures or query logs from a C-series, G-series, or other webOS model and
want to co-maintain this list, [open an issue](https://github.com/furkan-bayrak/lg-tv-blocklist/issues)
or submit a PR.

## License

Content and generated lists: [CC BY 4.0](LICENSE). Scripts and workflows:
[MIT](LICENSE-MIT).
