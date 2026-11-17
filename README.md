# LG TV Blocklist

DNS filtering for LG webOS advertising, ACR (Automatic Content Recognition)
and telemetry, with an optional aggressive service-blocking tier.
Use it with Pi-hole, AdGuard Home, NextDNS or another compatible blocker.
Not affiliated with LG Electronics. LG is a trademark of LG Corp.

## Which list should I use?

**Start with SAFE** for lower-disruption ad/telemetry filtering.
**Choose STRICT deliberately** to add firmware OTA, ThinQ/cloud and LG Channels
blocking, weak/inferred entries and broad zone anchors. It can also disrupt
store, streaming, clock or AirPlay dependencies.

Neither tier guarantees compatibility or stops every LG connection.
The historical German G1 audit, later reports and DNS-only sibling inferences
are different kinds of evidence. SAFE retains explicit exceptions, including
untested owner-directed `alphonso.tv`.
Read the **[project overview](docs/overview.md)** for the canonical
[compatibility table](docs/overview.md#compatibility), evidence policy,
[format-scope table](docs/overview.md#format-scope) and repository map.

## Install

Pick a tier above, then load the matching file into your blocker. Step-by-step walkthrough per blocker, with checks and uninstall steps: **[docs/install.md](docs/install.md)**.

| Your blocker | SAFE | STRICT |
|---|---|---|
| Pi-hole (v6) | [safe-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt) | [strict-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt) |
| AdGuard Home | [safe-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt) | [strict-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt) |
| dnsmasq | [safe-dnsmasq.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-dnsmasq.txt) | [strict-dnsmasq.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-dnsmasq.txt) |
| Rooted TV `/etc/hosts` | [safe-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-hosts.txt) | [strict-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-hosts.txt) |

**NextDNS:** [additive-only bulk import](docs/install.md#nextdns), not a URL
subscription. **Unbound:** [convert to local-data](docs/install.md#unbound-and-similar-resolvers).
**uBlock Origin:** the adblock file filters browser traffic, not your TV.

Optional regex: [safe-wildcard.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-wildcard.txt)
and [strict-wildcard.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-wildcard.txt).
Paste into Pi-hole **Regex filters**, not an adlist; AdGuard Home needs slash-wrapped custom rules.
These generalize explicitly tagged regional families, not all LG endpoints;
STRICT also includes zone anchors. [Regional guidance](docs/faq.md#im-not-in-germany--do-the-lists-still-work-for-me).

Checksums: [SHA256SUMS](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/SHA256SUMS).
Follow the [update/uninstall guide](docs/install.md#keeping-the-lists-up-to-date);
switching to SAFE does not remove stale manually imported STRICT rules.

## The two caveats

1. **Filtering only works on the path actually used.** Hardcoded DNS, DoH,
   IP-literal traffic and TV caches can bypass the expected resolver.
   The optional [rooted hooks](examples/webos-hooks/) redirect IPv4 port 53
   and drop supported port-853 traffic, but do not solve DoH, unsupported
   IPv6 or stale DNAT targets. Use generated `*-hosts.txt` for hosts-file
   deployments, not `src/strict.txt` (only a delta).
2. **Format changes coverage.** Domains/hosts are exact-name; adblock and
   dnsmasq reach descendants. Current dnsmasq rules use `address=/name/#`
   for null A (`0.0.0.0`) and AAAA (`::`) answers, with unchanged names
   and descendant scope. Hosts output remains IPv4-only. Older downloaded
   dnsmasq snippets retain their IPv4 limitation: replace and reload them,
   using a build accepting this syntax and `dnsmasq --test` before replacing
   live configuration. See the [install steps](docs/install.md#dnsmasq) and
   [official manual](https://dnsmasq.org/docs/dnsmasq-man.html).
   STRICT zone/regex rules reach unenumerated descendants, including shared
   services. Network-wide rules can affect non-TV devices.
   [Format scope and limitations](docs/overview.md#format-scope).

## Understand and contribute

- **[Project overview](docs/overview.md):** project map, tier decisions,
  compatibility evidence and unknowns. Reproduce source counts with
  `python3 scripts/build.py inventory`; counts are not tested-service counts.
- **[FAQ](docs/faq.md):** narrow store/AirPlay diagnostics, clock, DNS bypass
  and localization recipes.
- **[Methodology](docs/methodology.md):** contact, purpose and actual-scope
  compatibility evidence; [historical upstream record](docs/upstream.md).
- **[Contributing](CONTRIBUTING.md):** edit annotated sources, not generated
  `lists/`; run the relevant checks. [New-domain template](.github/ISSUE_TEMPLATE/01_new_domain.md)
  / [breakage template](.github/ISSUE_TEMPLATE/02_breakage.md).

More entries are not automatically better. Bring attributed evidence,
uncertainty and reproducible behavior, not a target list size.

## License

Content and generated lists: [CC BY 4.0](LICENSE). Scripts and workflows: [MIT](LICENSE-MIT).
