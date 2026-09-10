# Rooted webOS — DNS-egress hook

**What this is:** a webosbrew `init.d` hook that forces all TV-originated DNS
through *your* resolver. webOS daemons hardcode public resolvers
(`8.8.8.8` / `1.1.1.1`), so those queries never reach your LAN DNS — this
hook DNATs udp/tcp 53 to your resolver and drops DoT/DoQ (853) at the kernel,
closing the bypass.

**What this is not:** a blocklist. The blocking still comes from your
resolver's rules — this list, AdGuard Home, Pi-hole, NextDNS, etc. The hook
only makes sure the TV cannot route around them.

**Root required** (webosbrew / Homebrew Channel). Most ISP routers
(FRITZ!Box, Vodafone station, Comcast gateways) cannot do custom NAT
redirects — that is exactly why this runs on the TV.

## Install (3 steps)

1. Copy `02-block-dns-egress.sh` to
   `/var/lib/webosbrew/init.d/02-block-dns-egress` — **without the `.sh`
   extension**: webOS `run-parts` ignores dotted names. Then `chmod +x` it.
2. Run it once (`sh /var/lib/webosbrew/init.d/02-block-dns-egress`) or just
   reboot — it auto-detects your default gateway as the resolver. If your
   init runs before the network is up, hardcode `RESOLVER_IP` in the script.
3. **Verify from the TV:** `nslookup <a domain your list blocks> 8.8.8.8`
   must no longer return a public IP — and the query must appear in your
   resolver's log. Normal apps (Netflix, YouTube) must still work.

Failures are visible: the hook logs to `/var/log/02-block-dns-egress.log`
and syslog, and exits 1 (no success line) if any rule is missing.

## Rollback

One command: `sh rollback-dns-egress.sh` — it deletes every rule in a loop
until gone and prints `iptables -S` / `iptables -t nat -S` as a post-check.
Permanent removal: `rm /var/lib/webosbrew/init.d/02-block-dns-egress`, then
reboot.

## Caveats

- **No DNS fallback.** If your resolver is down, the TV loses DNS — the same
  exposure as any LAN device pointed at it.
- **DoH over 443 cannot be blocked** without breaking streaming; a daemon that
  ships its own DoH client can still escape.
- **The auto-detected resolver must actually serve DNS.** The hook points the
  TV at its default gateway — if that is not your resolver, hardcode it.
- **Changed gateway/resolver:** the hook appends rules and never reconciles an
  edited target — if your gateway or resolver changes, the old DNAT rule still
  wins. The rollback auto-detects the *current* gateway, so it will not match
  the old rule; remove it explicitly with
  `RESOLVER_IP=<old-gateway> sh rollback-dns-egress.sh`, or delete the nat
  OUTPUT rules by hand, then reinstall.
- **IPv6:** outbound IPv6 DNS (53/853) is DROPped only where `ip6tables`
  actually works — some kernels lack `ip6_tables`. Where it does not, the hook
  only logs a WARNING and IPv6 DNS stays **unfiltered**, so a global IPv6
  prefix can bypass enforcement. Check `/var/log/02-block-dns-egress.log`
  (the IPv6 line) to see which case you are in.
- **Portability:** needs an `iptables` that supports `-C` (very old builds
  re-add duplicates on every boot and the hook exits 1); if `iptables` isn't
  found, the hook exits without applying anything.

## Disclaimer

Provided as-is, no warranty — you are modifying your TV as root. Rollback is
provided; use it if anything misbehaves. License: MIT (see
[LICENSE-MIT](../../LICENSE-MIT)).
