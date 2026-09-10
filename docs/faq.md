# FAQ

Answers to the questions that come up most often. See the [README](../README.md) for install instructions, tier descriptions, and format semantics.

## Which tier should I use?

- **SAFE** — blocks ads, ACR, and telemetry while keeping everything functional (Content Store, app updates, OTA, ThinQ, streaming apps). The right choice for almost everyone. No root required: these are DNS lists — they work in Pi-hole, AdGuard Home, NextDNS, and similar.
- **STRICT** — SAFE's entries plus firmware OTA, ThinQ cloud sync, and LG Channels kill rows, plus zone anchors (whole-subtree blocks) and weak/unknown observations. It assumes you want the TV to stop talking to LG, not just stop being tracked. The Content Store may degrade — see the carve-out below.

Root is only required for the `/etc/hosts` install path on the TV itself. DNS-level blocking never needs root.

## Will this break Netflix / Prime / HBO / YouTube?

No. SAFE's promise — verified on an LG G1 — is that these keep working while ads, ACR, and telemetry die. STRICT keeps streaming working too; what it breaks by design is firmware OTA updates, ThinQ cloud sync, and LG Channels. The one functional risk in STRICT is the Content Store (below).

## I want STRICT but keep the LG Content Store

STRICT blocks whole zones (`||lge.com^`, `||lgeapi.com^`, `||nextlgsdp.com^`, ...) because store, update, telemetry, and account services all live inside those trees. To keep the store, carve out exceptions for the specific hosts it needs.

**The trap to avoid:** do NOT use umbrella exceptions like `@@||lge.com^`. That unblocks every `*.lge.com` host — including the firmware-OTA family (`snu`, `su`, `su-ssl`, `ngfts`, `gfts`) that STRICT exists to block. And in AdGuard, `$important` on an exception beats `$important` on a block (priority: important exception > important block > normal exception > normal block), so umbrella `$important` exceptions silently kill your own blocking rules. Our lists use no `$important`, so a plain `@@` exception is enough — only add `$important` if you are fighting another list's important blocks.

**Starting point (community-testing — not yet G1-verified; trim it with your own query log):**

```text
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
# @@||lgappstv.com^          (store thumbnails/CDN across subdomains)
# Unblock only if the TV shows offline / "no internet" UI quirks:
# @@||lgtvonline.lge.com^
```

Why these candidates: `lgeapi.com` is the region App Store backend (public reverse-engineering, e.g. webos-unclutter); `lgtvsdp.com` is LG's Service Delivery Platform ("responsible for Content Store communication among others" — webosbrew wiki); `nextlgsdp.com` may carry in-app billing; `lgappstv.com` is store-CDN-adjacent. STRICT annotates all of them as *store interplay unproven* — that is why this is a starting point, not gospel.

**Keep these blocked** even if the store keeps working (they are not needed for store/updates): the `snu`/`su`/`ngfts`/`gfts` firmware family, `lss.lgthinq.com`, `bss.lgechannel.com`, and — if you also run SAFE — `cdpbeacon.lgtvcommon.com` (ACR beacon, ~6-minute heartbeat), `ads.lgtvcommon.com`, and the `homeprv`/`recommend`/`eic.nudge`/`eic.wiseconfig` promos/telemetry family.

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

webOS TVs ship with a local stub resolver and hardcoded fallback DNS (`8.8.8.8` / `1.1.1.1`), so they can bypass your LAN DNS. Packet captures on our G1 confirmed the stub ignoring LAN DNS. Fix it at the router, not the TV: NAT-redirect outbound port 53 to your DNS server, and block outbound 853 (DNS-over-TLS) — optionally known DoH endpoints too. See the README's resolver caveats.

## Do exceptions work with the hosts-format lists?

AdGuard Home evaluates `@@` exceptions at the engine level, but the official docs only guarantee modifier semantics (`$important`, `$badfilter`) for rule-style filters — modifiers do not work with `/etc/hosts`-style entries. Our lists use no modifiers, so a plain `@@` exception works; still, for AdGuard Home we recommend the `-adblock.txt` URL anyway, because only the adblock format gives whole-zone semantics for STRICT's zone anchors.

## Why is a domain missing / how do I report a false positive?

See [CONTRIBUTING](../CONTRIBUTING.md) — the evidence bar is the point of this project. Use the issue templates.
