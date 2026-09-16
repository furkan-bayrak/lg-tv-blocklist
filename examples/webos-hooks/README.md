# Rooted webOS — example hooks

**What this is:** two webosbrew `init.d` boot hooks, shipped as copy-me
examples:

- **`02-block-dns-egress.sh`** — forces all TV-originated DNS through *your*
  resolver. webOS daemons hardcode public resolvers (`8.8.8.8` / `1.1.1.1`),
  so those queries never reach your LAN DNS — this hook DNATs udp/tcp 53 to
  your resolver and drops DoT/DoQ (853) at the kernel, closing the bypass.
- **`04-sync-clock.sh`** — sets the TV clock from an HTTP `Date:` header
  after cold boot. Blocking LG's time-sync domains can leave the TV stuck at
  `2021-01-01` after power loss, and a wrong clock breaks strict-TLS fetches
  (e.g. Homebrew Channel errors). Details: [the clock-sync hook
  below](#the-clock-sync-hook).

**What these are not:** a blocklist. The blocking still comes from your
resolver's rules — this list, AdGuard Home, Pi-hole, NextDNS, etc. The
DNS-egress hook only makes sure the TV cannot route around them.

**Root required** (webosbrew / Homebrew Channel). Most ISP routers
(FRITZ!Box, Vodafone station, Comcast gateways) cannot do custom NAT
redirects — that is exactly why the DNS hook runs on the TV.

## The DNS-egress hook

### Install (3 steps)

1. Copy `02-block-dns-egress.sh` to
   `/var/lib/webosbrew/init.d/02-block-dns-egress` — **without the `.sh`
   extension**: webOS `run-parts` ignores dotted names. Then `chmod +x` it.
2. Run it once (`sh /var/lib/webosbrew/init.d/02-block-dns-egress`) or just
   reboot — it auto-detects your configured DNS server via `connectionmanager`
   when available, falling back to your default gateway. If your init runs
   before the network is up, hardcode `RESOLVER_IP` in the script.
3. **Verify from the TV:** `nslookup <a domain your list blocks> 8.8.8.8`
   must no longer return a public IP — and the query must appear in your
   resolver's log. Normal apps (Netflix, YouTube) must still work.

Failures are visible: the hook logs to `/var/log/02-block-dns-egress.log`
and syslog, and exits 1 (no success line) if any rule is missing or if the
resolved target is refused (see the non-local resolver guard below).

### Rollback

One command: `sh rollback-dns-egress.sh` — it deletes every rule in a loop
until gone and prints `iptables -S` / `iptables -t nat -S` as a post-check.
Permanent removal: `rm /var/lib/webosbrew/init.d/02-block-dns-egress`, then
reboot.

### Caveats

- **No DNS fallback.** If your resolver is down, the TV loses DNS — the same
  exposure as any LAN device pointed at it.
- **DoH over 443 cannot be blocked** without breaking streaming; a daemon that
  ships its own DoH client can still escape.
- **The auto-detected resolver must actually serve DNS.** The hook reads the
  TV's configured DNS server from `connectionmanager` and only falls back to
  the default gateway when that fails — if neither is your resolver, hardcode
  it; see [how the hook picks its resolver, and how to override
  it][faq-resolver].
- **Non-local resolver guard.** The DNAT target must be a private, loopback or
  link-local address. If the detected DNS is public (a DHCP-pushed `8.8.8.8`,
  a VPN resolver), the hook skips the DNAT rules, logs an ERROR and exits 1
  instead of silently enshrining it; the resolver-independent 853 DROP rules
  still apply. Set `ALLOW_NON_LOCAL_RESOLVER=1` only if that target is
  intentional (logs a WARNING and continues).
- **Changed resolver:** the hook appends rules and never reconciles an
  edited target — if your resolver or gateway changes, the old DNAT rule still
  wins. The rollback auto-detects the *current* resolver the same way, so it
  will not match the old rule; remove it explicitly with
  `RESOLVER_IP=<old-resolver> sh rollback-dns-egress.sh`, or delete the nat
  OUTPUT rules by hand, then reinstall.
- **IPv6:** outbound IPv6 DNS (53/853) is DROPped only where `ip6tables`
  actually works — some kernels lack `ip6_tables`. Where it does not, the hook
  only logs a WARNING and IPv6 DNS stays **unfiltered**, so a global IPv6
  prefix can bypass enforcement. Check `/var/log/02-block-dns-egress.log`
  (the IPv6 line) to see which case you are in.
- **Portability:** needs an `iptables` that supports `-C` (very old builds
  re-add duplicates on every boot and the hook exits 1); if `iptables` isn't
  found, the hook exits without applying anything.

## The clock-sync hook

**Why:** on some TVs (verified on our rooted G1) the RTC resets to
`2021-01-01` on cold boot / power loss, and LG's built-in time sync uses SDP
endpoints that the lists block — so the clock never recovers on its own. Every
strict-TLS fetch then fails with *"certificate is not yet valid"*, e.g.
the Homebrew Channel repo download dies with error `(0)`. Symptom write-up:
[FAQ][faq-clock].

### Install (3 steps)

1. Copy `04-sync-clock.sh` to
   `/var/lib/webosbrew/init.d/04-sync-clock` — **without the `.sh`
   extension**: same `run-parts` rule as above. Then `chmod 755` it.
2. Run it once (`sh /var/lib/webosbrew/init.d/04-sync-clock`) and check
   `date` — if the clock is wrong it jumps to the real time. A clock whose
   year is already sane (2024–2100) is left alone without any network fetch.
3. Nothing else — every boot now self-corrects the clock; a failed sync is
   logged and never blocks boot.

Failures are visible: the hook logs `OK:`/`WARN:` lines to
`/tmp/webosbrew_hook.log` (prefixed `04-sync-clock:`). Force specific URLs
with `SYNC_URLS_OVERRIDE="http://url1/ http://url2/"`.

### Rollback

One command: `sh rollback-sync-clock.sh` — removes the hook file and prints
the `init.d` listing plus the current date as a post-check. The clock value
itself is not (and does not need to be) reverted; no reboot needed.

### Caveats

- **Plain HTTP only, by design.** HTTPS needs a correct clock to validate
  certificates, so the fetch runs over port 80 and only the `Date:` header is
  read. Point it at URLs you trust via `SYNC_URLS_OVERRIDE` if you prefer.
- **Parallel, bounded fetches.** All URLs are tried at once with a 4-second
  cap each; a second round only runs when none answered. A dead network adds
  ~8 seconds to boot, never a timeout queue — and an already-sane clock costs
  no network at all.
- **Corroborated before set.** When two or more sources answer, their times
  must agree within 120 seconds or the clock is not set (`WARN`, possible
  tampering). A single responder is accepted but flagged `WARN` — it cannot be
  corroborated.
- **Validated dates.** Impossible `Date` values (day `32`, `31 Feb`, hour
  `99`, ...) and implausible years are rejected instead of being shifted into
  the clock.
- **Year-implausible clocks only, by design.** The fast path treats any clock
  in 2024–2100 as sane, so the hook corrects power-loss resets (e.g. a
  `2021-01-01` clock) but leaves a clock that is months or days off alone —
  only a wrong-by-year clock triggers a fetch and is overwritten.
- **Boot safety over loud failure:** unlike the DNS hook, this one always
  exits 0 — a failed sync is a logged `WARN`, never a reason to hold up boot.
- **Timezone comes from the TV.** The server sends UTC and the hook converts
  it through the system timezone; a misconfigured TV timezone still shows the
  wrong wall-clock time.

## Disclaimer

Provided as-is, no warranty — you are modifying your TV as root. Rollback is
provided; use it if anything misbehaves. License: MIT (see
[LICENSE-MIT](../../LICENSE-MIT)).

[faq-resolver]: ../../docs/faq.md#how-does-the-dns-egress-hook-pick-its-resolver_ip
[faq-clock]: ../../docs/faq.md#homebrew-channel--https-apps-fail-after-power-loss-or-cold-boot
