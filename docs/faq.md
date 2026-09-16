# FAQ

Answers to the questions that come up most often. See the [README](../README.md) for tier descriptions, the [install guide](install.md) for step-by-step setup, and [CONTRIBUTING.md](../CONTRIBUTING.md#format-semantics) for format semantics.

## Which tier should I use?

- **SAFE** — blocks ads, ACR, and telemetry while keeping everything functional (Content Store, app updates, OTA, ThinQ, streaming apps). The right choice for almost everyone. No root required: these are DNS lists — they work in Pi-hole, AdGuard Home, NextDNS, and similar.
- **STRICT** — SAFE's entries plus firmware OTA, ThinQ cloud sync, and LG Channels kill rows, plus zone anchors (whole-subtree blocks) and weak/unknown observations. It assumes you want the TV to stop talking to LG, not just stop being tracked. The Content Store may degrade — see the carve-out below.

Root is only required for the `/etc/hosts` install path on the TV itself. DNS-level blocking never needs root.

## Will this break Netflix / Prime / HBO / YouTube?

No. SAFE's promise — verified on an LG G1 — is that these keep working while ads, ACR, and telemetry die. STRICT keeps streaming working too; what it breaks by design is firmware OTA updates, ThinQ cloud sync, and LG Channels. The functional risks in STRICT are the Content Store and LG account login (see the README breakage matrix); the carve-out below addresses the store.

Disney+ and other streaming apps were not part of the G1 smoke test: SAFE is expected to leave them working (they use their own infrastructure, none of which is on the list), but that is inference, not tested evidence.

## I want STRICT but keep the LG Content Store

STRICT blocks whole zones (`||lge.com^`, `||lgeapi.com^`, `||nextlgsdp.com^`, ...) because store, update, telemetry, and account services all live inside those trees. To keep the store, carve out exceptions for the specific hosts it needs.

**The trap to avoid:** do NOT use umbrella exceptions like `@@||lge.com^`. That unblocks every `*.lge.com` host — including the firmware-OTA family (`snu`, `su`, `su-ssl`, `ngfts`, `gfts`) that STRICT exists to block. And in AdGuard, `$important` on an exception beats `$important` on a block (priority: important exception > important block > normal exception > normal block), so umbrella `$important` exceptions silently kill your own blocking rules. Our lists use no `$important`, so a plain `@@` exception is enough — only add `$important` if you are fighting another list's important blocks.

**Starting point (community-testing — not yet G1-verified; trim it with your own query log):**

```text
# SDP/store comms — needed with the adblock lists (our ||lgtvsdp.com^ covers de.); domains/hosts users can drop it:
@@||de.lgtvsdp.com^
@@||de.lgeapi.com^
@@||de.ibs.nextlgsdp.com^
@@||a.lgappstv.com^
# Add only if your query log shows the store hitting them:
# @@||qt2-ngp-gl-prv-front.lge.com^
# @@||alkas.lge.com^
# @@||aic-updr.lge.com^
# @@||snsu.lge.com^
# @@||service.lgtvcommon.com^
# Thumbnails: whitelist the EXACT lgappstv.com host from your log — never the
# lgappstv.com umbrella (it also carries ad.lgappstv.com, an ad host):
# @@||<exact-host>.lgappstv.com^
# Unblock only if the TV shows offline / "no internet" UI quirks:
# @@||lgtvonline.lge.com^
```

**Region prefixes:** the `de.` hosts above are what the German G1 audit saw — if your TV is in another region, swap `de.` for your prefix (`fr.`, `uk.`, `us.`, …) and confirm the exact hostnames against your query log. The blocked zones themselves are region-agnostic in the adblock lists (`||lgeapi.com^` also covers `fr.lgeapi.com`), so only the exceptions need adjusting.

Confidence varies — that is why this is a starting point, not gospel. STRICT annotates `de.lgeapi.com` as *store/billing interplay unproven* and `de.ibs.nextlgsdp.com` as *store risk* (both are caught by their zone anchors), and `a.lgappstv.com` as *app-update function unproven*. External sources fill the rest: `lgeapi.com` is the region App Store backend (public reverse-engineering, e.g. webos-unclutter); `lgtvsdp.com` is LG's Service Delivery Platform ("responsible for Content Store communication among others" — webosbrew wiki) — our SAFE tier blocks its apex, so with the adblock lists `||lgtvsdp.com^` covers `de.lgtvsdp.com` and this exception is needed for store comms; with domains/hosts lists (exact-name) it is unnecessary; `nextlgsdp.com` may carry in-app billing; `lgappstv.com` is the store CDN apex.

**Keep these blocked** even if the store keeps working: the `snu`/`su`/`su-ssl`/`ngfts`/`gfts` firmware-OTA and file-transfer family (not required for store function — if store thumbnails ever break, whitelist only the exact host from your log), `lss.lgthinq.com`, `bss.lgechannel.com`, plus the ad/telemetry hosts that STRICT already includes from SAFE: `cdpbeacon.lgtvcommon.com` (ACR beacon, ~6-minute heartbeat), `ads.lgtvcommon.com`, and the `homeprv`/`recommend`/`eic.nudge`/`eic.wiseconfig` family.

**ACR beacon:** the bare `cdpbeacon.lgtvcommon.com` is dead (NXDOMAIN, annotated DECOMMISSIONED) — its live successor twins, `eic.`/`aic.`/`kic.cdpbeacon.lgtvcommon.com`, are STRICT-only and tagged `weak`, so SAFE currently has no ACR-beacon coverage. It returns to SAFE if and when traffic observation lands.

**How to verify on your network (AdGuard Home):**

1. Add the exceptions above as custom filtering rules (Filters → Custom filtering rules).
2. Query log → filter by the TV's IP → clear.
3. On the TV: open the store, browse, install a new app, update an app, reboot.
4. Look for blocked entries under `lge.com` / `lgeapi.com` / `nextlgsdp.com` / `lgappstv.com` / `lgtvsdp.com` / `lgtvcommon.com` that coincide with something failing — whitelist only those exact hosts.
5. Let it run for a day and confirm `cdpbeacon.lgtvcommon.com` stays blocked and the store still works.
6. Report your final set via the issue tracker — verified sets get folded into this recipe with credit.

## Why doesn't SAFE block all of lge.com instead of individual hosts?

Because `lge.com` is an umbrella zone: blocking it kills the Content Store, firmware updates, and account login along with the telemetry. SAFE only blocks hosts with observed ad/telemetry behavior (exact-name semantics). Whole-zone blocking is the STRICT philosophy — stronger, with documented collateral damage.

## My TV ignores my Pi-hole / AdGuard. Why?

webOS TVs ship with a local stub resolver and hardcoded fallback DNS (`8.8.8.8` / `1.1.1.1`), so they can bypass your LAN DNS. Packet captures on our G1 confirmed the stub ignoring LAN DNS. Fix it at the router, not the TV: NAT-redirect outbound port 53 to your DNS server, and block outbound 853 (DNS-over-TLS) — optionally known DoH endpoints too. On a rooted TV (webosbrew), [`examples/webos-hooks/`](../examples/webos-hooks/) has a ready-made hook that applies the port-53 redirect and the 853 drop on-device. See the README's resolver caveats.

## Can IPv6 bypass my blocklist?

Yes, when your redirect is IPv4-only. The usual setup (see [caveat 1](../README.md#the-two-caveats)) NATs outbound IPv4 port 53 to your resolver and drops 853. A TV with a global IPv6 address does not need IPv4 DNS: if your router advertises DNS servers over IPv6 (RDNSS in its router advertisements), the TV can query those directly over IPv6 and the v4 rules never see the packet. Encrypted DNS over IPv6 (853) slips through the same way.

**How to check:**

- Router admin: does your IPv6 setup advertise DNS servers (look for RDNSS, IPv6 DNS, or an "advertise DNS" option)?
- Query log: with IPv6 enabled, do the TV's queries still arrive? A TV that is clearly online but never appears in the log is the signature. The query-log step is in the [install guide](install.md#after-install).

**Cheapest fixes, router first:**

1. Point the DNS servers advertised over IPv6 at your resolver's IPv6 address, or turn the IPv6 DNS advertisement off so the TV falls back to IPv4.
2. Firewall IPv6 udp/tcp 53 and 853 outbound, allowing only your resolver (the v6 twin of the v4 rule).
3. Disable IPv6 on the LAN, if nothing else on your network needs it.

**Rooted TV:** the [`02-block-dns-egress` hook](../examples/webos-hooks/02-block-dns-egress.sh) already drops IPv6 53 and 853 where `ip6tables` works. Some kernels lack it, and the hook logs a `WARNING:` instead of filtering; check `/var/log/02-block-dns-egress.log` and the [hook caveats](../examples/webos-hooks/README.md#caveats).

**Honest note:** the fixes above depend on your router, and our own G1 could not test them: its IPv6 guard hit the no-`ip6tables` case, so the hook's v6 drops are untested on our hardware.

## How does the DNS-egress hook pick its `RESOLVER_IP`?

It tries, in order:

1. **`RESOLVER_IP` override** — if you set it (environment variable or hardcoded), that wins.
2. **The TV's configured DNS server** — `dns1` read from `com.webos.service.connectionmanager/getStatus`. This works on webOS 6.x (verified on our rooted G1). The first usable IPv4 `dns1` is used; IPv6 values and `0.0.0.0` are skipped, and disconnected interfaces omit the dns fields entirely.
3. **The default-route gateway** — the fallback, used when the API is unavailable (older firmware, boot before the network is up, `luna-send` missing).

`/etc/resolv.conf` is a dead end: it points at a localhost stub (`127.0.0.1` / `::1`) and reveals nothing about the configured DNS — that is why the hook asks connectionmanager instead.

That matters because if detection does fall back to the gateway and your router forwards DNS to your own resolver, queries still get answered — but they arrive via the router/gateway: per-device attribution is lost, and depending on the router's config they may bypass your resolver and its filtering entirely.

**Point it at your own resolver:** set `RESOLVER_IP` to your resolver's IP — hardcoded near the top of `02-block-dns-egress.sh` (most reliable, since the init environment may not pass environment variables) or as an environment variable:

```sh
RESOLVER_IP=192.168.178.53 sh /var/lib/webosbrew/init.d/02-block-dns-egress
```

**Already ran the hook this boot?** Changing `RESOLVER_IP` on a re-run does not replace the old rule — the hook only appends, so the stale DNAT rule stays first-match and keeps winning, while the success line still reports the new IP. Remove the old rules first with `sh rollback-dns-egress.sh` (it auto-detects the same resolver the hook picks; pass `RESOLVER_IP=<old-resolver>` if the rules were created with a different one), then re-run with your `RESOLVER_IP` — or hardcode it and reboot: the kernel rules are rebuilt empty at boot.

**Verify:** the hook logs the resolver it chose and where it came from — look for `resolver: <IP> (source: environment|connectionmanager|default-route gateway)` in `/var/log/02-block-dns-egress.log` (fallback `/tmp/02-block-dns-egress.log`); the success line `dnat 53 -> <IP>` carries the same IP.

## Homebrew Channel / HTTPS apps fail after power loss or cold boot

**Symptom:** after power loss or any cold boot, HTTPS downloads start failing — e.g. the Homebrew Channel cannot fetch its repo or install apps and errors out with `(0)`, or apps report TLS errors like *"certificate is not yet valid"*.

**Cause:** the TV clock is stuck at `2021-01-01`. On our rooted G1 the RTC does not survive power loss, and the TV's built-in time sync talks to LG's SDP time endpoints (`lgtvsdp.com` / `nextlgsdp.com` families) — which the lists block — so the clock never recovers. Every strict-TLS connection is then rejected as "not yet valid". This is a known side effect of blocking LG's time domains.

**Quick check (root/SSH):** run `date` on the TV — if it shows a 2021 date, this is the same problem.

**Fix:** install the [`04-sync-clock` hook](../examples/webos-hooks/04-sync-clock.sh) — it sets the clock at boot from the `Date:` header of a plain-HTTP request (no NTP tools needed). Install steps: [hook README](../examples/webos-hooks/README.md#the-clock-sync-hook).

**Temporary manual fix (root/SSH):** set the clock once by hand, e.g. `date -s '2026-09-16 12:00:00'` — it will reset again on the next cold boot until the hook is installed.

## Why aren't `in-addr.arpa` / LAN discovery queries blocked?

Because they never leave the LAN. Reverse lookups under `in-addr.arpa` are answered by your local resolver in milliseconds, and discovery protocols (SSDP, mDNS) are link-local multicast — adding them to a DNS blocklist would not stop a TV from enumerating the LAN, it would only break reverse name resolution for everything else using that resolver. Stopping the scan itself needs device- or network-level rules (firewall drops of discovery traffic on a rooted TV or at the router), and expect that to break discovery-dependent features like casting. If the concern is the cloud side of the feature, the STRICT entry `ueiwsp.com` (QuickSet Cloud) covers it.

## Do exceptions work with the hosts-format lists?

AdGuard Home evaluates `@@` exceptions at the engine level, but the official docs only guarantee modifier semantics (`$important`, `$badfilter`) for rule-style filters — modifiers do not work with `/etc/hosts`-style entries. Our lists use no modifiers, so a plain `@@` exception works; still, for AdGuard Home we recommend the `-adblock.txt` URL anyway, because only the adblock format gives whole-zone semantics for STRICT's zone anchors.

## I'm not in Germany — do the lists still work for me?

Depends on your tier and format. In **adblock** format, **STRICT is region-complete**: its zone anchors (`||lgeapi.com^`, `||nextlgsdp.com^`, ...) and apex entries (`||lgsmartad.com^`, `||lgtvsdp.com^`) match every subdomain, including region-prefixed hosts like `fr.lgeapi.com` and `fr.nextlgsdp.com`.

**SAFE's adblock list only covers region siblings under the apexes it actually contains.** It blocks the `lgsmartad.com` and `lgtvsdp.com` families wholesale (`||lgsmartad.com^`, `||lgtvsdp.com^`), so `fr.info.lgsmartad.com` and `fr.lgtvsdp.com` are caught. But `nextlgsdp.com` and `lgsmartplatform.com` are STRICT-only zones: SAFE has no `||nextlgsdp.com^` or `||lgsmartplatform.com^`, so `fr.nextlgsdp.com` and `fr.emp.lgsmartplatform.com` are **not** covered by SAFE's adblock list.

The **domains/hosts formats are exact-name** for everyone: `de.lgeapi.com` does not block `fr.lgeapi.com`, and hosts files cannot wildcard subdomains — so those formats only cover the region prefixes present in the lists, and they are where `localize.py` matters most.

For exact-name use outside Germany, the built lists cover the audited prefixes (`de.`, `us.`, `ca.` today). For anywhere else, localize them and repeat the run after every list update:

```sh
python scripts/localize.py --region fr
```

That writes `lists-regions/fr/` (all 6 lists plus `SHA256SUMS`), rewriting only entries with an audited prefix (`de.`, `us.`, `ca.` today). The output header marks the result **unaudited**: most endpoints for your region were never observed in our German audit, so verify against your own query log before relying on them.

**Use your TV's real prefix.** Take it from the query log: LG does not always serve a country under its ISO code, for example `uk.`, not `gb.`. A wrong prefix rewrites nothing and blocks nothing.

**Serve the output to your blocker.** The files land on the machine that ran the script; copy the `lists-regions/<cc>/` files to wherever your blocker reads lists from, or serve the directory over HTTP from a machine on your LAN (any static file server, for example `python -m http.server`) and subscribe to that URL.

**Which path should you take?**

| Your blocker | What to do |
|---|---|
| Pi-hole / AdGuard Home | Subscribe to the normal list and add the `-wildcard.txt` regex lines; they cover every country, so there is nothing to re-run. |
| Exact-name only (hosts files, plain domains, some routers) | Localize and serve the output, and repeat after every list update. |
| NextDNS | No regex and no list URLs: add zone anchors as plain denylist entries, then canary-test. |
| Rooted TV `/etc/hosts` | The localized `-hosts.txt` must be redeployed to the TV, which resets on reboot; keep your copy somewhere persistent. |

**If your blocker does regex, there is regional coverage the exact-name lists cannot give you.** `lists/safe-wildcard.txt` generalises audited region-prefixed hosts to any country code (`^[a-z][a-z]\.nextlgsdp\.com$` covers `fr.`, `br.` and `jp.` alike) and matches two-letter prefixes only, so the family apex and longer labels such as `ngfts.` (updates) and `ibs.` (billing) stay reachable. `lists/strict-wildcard.txt` adds the `src/zones.txt` anchors in regex form, which block whole families by design, exactly as STRICT already does in the adblock format. These are pasted rules, not subscriptions; re-paste them after list updates (see the [install guide](install.md#keeping-the-lists-up-to-date)).

Both files go in Pi-hole's **Regex filters**, never an adlist: an adlist ignores every line and reports no error. In AdGuard Home the same lines work, wrapped in slashes (`/^[a-z][a-z]\.nextlgsdp\.com$/`) and added as a custom filtering rule. In STRICT the adblock list already covers the same families; in SAFE it only carries the audited countries, so these lines are where the rest comes from. They supplement a list subscription rather than replacing it: audited hosts with no region prefix and no zone anchor have no line in either file.

**NextDNS** can't use them at all (no regex support). For whole-family reach, add a zone anchor itself as a plain denylist entry (`lgtvcommon.com`), because subdomains are blocked automatically, with the same widening caveat as STRICT. For the full list, [`scripts/nextdns_sync.py`](../scripts/nextdns_sync.py) bulk-adds a list file to your NextDNS denylist. It dry-runs by default and only writes with `--apply`; the API key goes in the `NEXTDNS_API_KEY` environment variable. See the [install guide](install.md#nextdns).

One warning for `strict-wildcard.txt`: whole-zone blocking is new if you were on the exact-name lists, so read [keeping the Content Store](#i-want-strict-but-keep-the-lg-content-store) first. Note also that its `@@||host^` exceptions are AdGuard syntax; in Pi-hole an allowlist entry is an exact domain or its own regex.

If you have a query log for your region, it is exactly the evidence needed to extend the `de.*`/`us.*`/`ca.*` entries upstream: see [regional query logs welcome](../CONTRIBUTING.md#1-evidence-over-guesses). A prefix confirmed by a query log is added to `SOURCE_REGION_LABELS` so future `localize.py` runs rewrite it automatically.

## Why is a domain missing / how do I report a false positive?

See [CONTRIBUTING](../CONTRIBUTING.md) — the evidence bar is the point of this project. Use the issue templates.
