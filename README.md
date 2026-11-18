<div align="center">

# LG TV Blocklist

**Your TV. Your network. Your rules.**

Reduce unwanted advertising and tracking-related traffic from LG webOS TVs with community-maintained DNS blocklists.

[![Build blocklists](https://github.com/furkan-bayrak/lg-tv-blocklist/actions/workflows/build.yml/badge.svg?branch=main)](https://github.com/furkan-bayrak/lg-tv-blocklist/actions/workflows/build.yml) [![Lists: CC BY 4.0](https://img.shields.io/badge/lists-CC%20BY%204.0-586069)](#license)

**[Choose a list](#which-list-should-i-use)** · **[Quick start](#install)** · **[Documentation](#documentation)**

</div>

## Which list should I use?

**Start with SAFE.** STRICT trades compatibility for broader blocking.

| | SAFE | STRICT |
| :--- | :--- | :--- |
| **Goal** | Block ad and telemetry endpoints while prioritizing compatibility | Block more LG services |
| **Targets** | Ads, automatic content recognition (ACR), and telemetry | SAFE plus firmware updates, ThinQ cloud, LG Channels, and broader rules |
| **Risk** | Aims to preserve apps and updates | Store, streaming, time sync, and AirPlay can break |
| **For** | Most TV owners | Users who can troubleshoot feature loss |

SAFE has [documented exceptions](docs/methodology.md#from-data-to-tiers),
including `alphonso.tv`, which this project has not independently tested.
STRICT includes some lower-confidence entries. Check the
[compatibility evidence](docs/overview.md#compatibility) for knowns and unknowns.

## Install

Choose your blocker below and follow its setup guide to add the matching list.
If you're new to the project, use the SAFE column.

| Blocker & setup | SAFE | STRICT |
| :--- | :--- | :--- |
| [Pi-hole v6](docs/install.md#pi-hole-v6) | [SAFE domains](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt) | [STRICT domains](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt) |
| [AdGuard Home](docs/install.md#adguard-home) | [SAFE filter](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt) | [STRICT filter](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt) |
| [dnsmasq](docs/install.md#dnsmasq) | [SAFE config](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-dnsmasq.txt) | [STRICT config](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-dnsmasq.txt) |
| [Rooted TV](examples/webos-hooks/) | [SAFE hosts](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-hosts.txt) | [STRICT hosts](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-hosts.txt) |

[NextDNS](docs/install.md#nextdns) uses an additive denylist import, not a URL
subscription. [Unbound](docs/install.md#unbound-and-similar-resolvers) needs
conversion to `local-data`. The filter also works in uBlock Origin, but that
covers only your browser, not the TV.

**After setup:** [verify TV queries and blocking](docs/install.md#after-install).
The install guide covers [updates](docs/install.md#keeping-the-lists-up-to-date)
and [uninstalling](docs/install.md#uninstall). Downloads have a
[SHA256 manifest](lists/SHA256SUMS); verify files from the same commit.
When switching to SAFE, remove any manually imported STRICT rules.

<a name="from-traffic-to-rules"></a>

## How we build the lists

The lists began with a network audit of an LG G1 in Germany.

1. **Observe.** Correlate per-device DNS logs with packet captures to see what
   the TV contacts, including traffic the resolver log misses.
2. **Investigate.** Compare root-level webOS service observations with attributed
   community reports. A DNS answer or a connection does not establish purpose.
3. **Test and annotate.** Adding or promoting a SAFE entry requires
   established ad or telemetry purpose and a blocking test of the actual
   rule. Record the evidence and its limits in [`src/`](src/).

The audit didn't test every rule in today's lists.

[Read or reproduce the methodology →](docs/methodology.md)

<a name="the-two-caveats"></a>

## Limitations and compatibility

1. **A blocklist can only filter DNS it sees.** Hardcoded resolvers, DoH,
   IPv6 DNS bypass, cached answers, and direct IP connections can evade
   filtering. A hosts file alone is not enough. The optional rooted
   [DNS-egress hook](examples/webos-hooks/README.md#the-dns-egress-hook)
   has [its own limits](examples/webos-hooks/README.md#caveats).
2. **The format changes what gets blocked.** Domains and hosts files match
   exact names; adblock, dnsmasq, and NextDNS also match descendants. A
   network-wide STRICT rule can affect other devices. Current dnsmasq
   snippets sinkhole A and AAAA. [Validate and replace older IPv4-only copies](docs/install.md#dnsmasq).
   Hosts files remain IPv4-only. For optional regex and missing regional
   entries, see the [regional guide](docs/faq.md#im-not-in-germany--do-the-lists-still-work-for-me)
   and [format scope](docs/overview.md#format-scope).

## Documentation

- **[Install guide](docs/install.md)** — blocker setup, verification, and rollback.
- **[Project overview](docs/overview.md)** — compatibility by feature, rule
  scope, and the annotated source inventory.
- **[Troubleshooting FAQ](docs/faq.md)** — Content Store, AirPlay, clock,
  and DNS bypass.
- **[Upstream record](docs/upstream.md)** — submissions to other community blocklists.

## Contribute

Device logs and reproducible reports help fill gaps across models, firmware,
and regions. Include the model, firmware build, region, and sanitized evidence.
Use the [new-domain](.github/ISSUE_TEMPLATE/01_new_domain.md) or
[breakage](.github/ISSUE_TEMPLATE/02_breakage.md) template, or follow the
[contribution guide](CONTRIBUTING.md) and edit `src/`, not generated `lists/`.

## License

Content and generated lists: [CC BY 4.0](LICENSE). Scripts and workflows: [MIT](LICENSE-MIT).

Not affiliated with LG Electronics. LG is a trademark of LG Corp.
