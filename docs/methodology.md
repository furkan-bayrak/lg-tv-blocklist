# Methodology — how this list was built (and how to replicate it)

This list is the output of a two-week root-level audit of an LG G1 running
webOS: a ~44,800-packet capture, a 267,000-query DNS log, and per-service
investigation (root access, service kills, iptables, hosts hooks). Every
entry in `src/` traces back to that data — it was authored from audit data,
not scraped from other lists.

## The two-layer method

Two independent observation layers, each with its own blind spots:

| Layer | What it shows | What it misses |
|---|---|---|
| **DNS** — logging resolver (Pi-hole, AdGuard Home, …) plus per-client attribution | domain names, query timing, who asked | anything resolved outside your resolver (hardcoded DNS, DoT/DoH) |
| **Packet** — capture on a gateway or mirror port | DNS as well, plus TLS SNI and IP-literal traffic | encrypted payloads; requires the TV's traffic to traverse the capture point |

The DNS layer is the minimum. The packet layer catches the traffic DNS never
sees — and verifies the DNS story instead of trusting it.

## The gotcha that breaks naive setups

Point the TV at your resolver, watch the log, and it looks suspiciously
clean — so you conclude "no telemetry". That conclusion is wrong. webOS runs
a local stub resolver on `127.0.0.1:53` that does **not** read `/etc/hosts`,
and daemons hardcode public resolvers (`8.8.8.8` / `1.1.1.1`) as fallback.
Queries answered through those paths never appear in your log.

Observed evidence from the audit: `nslookup <host> 127.0.0.1` returned a real
upstream CNAME (the stub forwarding upstream), while `getent hosts <host>` on
the same TV returned the local null-route — the hosts file and the stub
resolver disagree about the same name.

Fix:

- Redirect the TV's outbound port 53 to your resolver at the firewall.
- Block outbound port 853 (DoT) — and known DoH endpoints if you can.
- On a rooted TV, a hosts hook is defense-in-depth, not a substitute for
  DNS-layer interception: only libc/NSS lookups (`getent hosts ...`) read
  `/etc/hosts`, so daemons that query the local stub directly still get
  real upstream answers and escape the hook.

Rooted via webosbrew? [`examples/webos-hooks/`](../examples/webos-hooks/)
ships a ready-made `init.d` hook that performs the port-53 redirect and the
853 drop on the TV itself.

## Setup options

Three tiers of effort:

1. **DNS-only (no root).** Run a logging resolver on an always-on host,
   NAT-redirect the TV's outbound port 53 to it, and block outbound 853
   (DoT) at the firewall. This is the minimum viable setup — but without the
   redirect, see the gotcha above: your log lies.
2. **+ packet capture.** Make the TV's traffic physically traverse a capture
   host: point the TV's default route at a laptop (forwarding enabled) or
   mirror the TV's switch port. Catches hardcoded-resolver queries and
   non-DNS traffic, and verifies the DNS story.
3. **+ root (Homebrew Channel).** sshd, hosts hooks (rewrite the tmpfs
   `/etc/hosts` at every boot), service kills, iptables. Root shrinks the
   baseline: kill what you understand, then whatever still talks is
   genuinely unknown — the residual set is where the weak/STRICT candidates
   live.

## Packet capture recipe

Commands from the audit, with placeholders. Route the TV through the capture
host first — temporary, since webOS connman owns routing (restore it after):

```sh
ip route replace default via <CAPTURE-HOST-IP>
```

Capture only the TV's traffic. Keep windows short — ~10–15 minutes of
scripted activity is enough:

```sh
dumpcap -i <IFACE> -f "host <TV-IP>" -w tv-audit.pcap
```

Note: `-a duration:...` auto-stop proved unreliable in the audit — stop the
capture manually.

Analyze offline:

```sh
# DNS names the TV asked for
tshark -r tv-audit.pcap -Y "dns.flags.response==1" -T fields -e dns.qry.name | sort -u

# Destinations the TV sent traffic to
tshark -r tv-audit.pcap -Y "ip.src==<TV-IP>" -T fields -e ip.dst | sort -u

# TLS SNI — names from TLS handshakes, including non-DNS traffic
tshark -r tv-audit.pcap -Y "tls.handshake.extensions_server_name" -T fields -e tls.handshake.extensions_server_name | sort -u
```

Caveat: same-interface forwarding is lossy — expect streaming to break
during capture windows. That is expected, not a finding.

## DNS-log correlation

Filter the resolver's query log by the TV's client IP. Don't chase one-off
hits; look for structure:

- **Boot bursts** — a cluster of names in the minutes after power-on
  (provisioning, initial setup, update checks).
- **Heartbeats** — queries at a fixed cadence. The audit's ACR beacon
  (`cdpbeacon.lgtvcommon.com`) queried roughly every 6 minutes; a pattern
  like that is far stronger evidence than a single random hit.

Client attribution is what makes the log useful: without it, you can't tell
the TV's queries from every other device on the network.

## From data to tiers

For each observed domain:

1. **Annotate it** — function plus evidence, per the
   [contribution contract](../CONTRIBUTING.md#2-edit-src-never-lists).
2. **Assign a tier:**
   - **SAFE** — only after app smoke tests verify no functional impact:
     Netflix, Prime, HBO, YouTube, Content Store, app install/update all
     still work.
   - **STRICT** — functional risk (OTA, ThinQ, LG Channels) or weak
     evidence. Weak entries never risk the SAFE promise.
   - **ZONE** — family apexes for whole-zone blocking where we haven't
     enumerated the whole family. Note: whole-zone blocking only works in
     the adblock format — `-domains.txt` / `-hosts.txt` block the apex name
     only (see [Format semantics](../README.md#format-semantics)).

## Firmware diff: "what's new in this update"

You can reuse the capture recipe to see exactly what a firmware update
changes. Run the **same scripted activity** before and after the update:

1. Boot → standby → wake.
2. Open each streaming app once.
3. Browse the Content Store.
4. Install or update one app.
5. Stream something for a few minutes.

Capture each run, extract the sorted DNS name set from each, and diff:

```sh
comm -13 before.txt after.txt   # names new in the after capture
```

Caveat: STRICT blocks the OTA domains by design, so the TV can't update
while those blocks are active. Run the diff capture with OTA **allowed**
(temporarily), update, re-capture, then re-apply the blocks.

Watch region prefixes: endpoints are often region-scoped (`de.`, `fr.`,
`uk.`, `us.`, …). A run in one region will not reveal another region's
endpoints.

## Submitting your data

Two paths:

- **Have evidence but no PR?** Open an issue with the
  [`new-domain` template](../.github/ISSUE_TEMPLATE/01_new_domain.md).
- **Ready to edit?** PR against `src/` only — never `lists/`, which is
  generated and CI-rejected. Details in [CONTRIBUTING.md](../CONTRIBUTING.md).

What counts as evidence:

- A querylog line with domain + client + timestamp. Boot-burst or heartbeat
  beats a single hit.
- A capture line with `dns.qry.name` or TLS SNI.
- Repro steps: what you did to trigger it.
- Device + webOS version (include your firmware build if you have it — see
  limitations).
- Suggested tier.
- For breakage reports: the symptom.

## Known limitations

- **One model, one region.** The audit covered an LG G1 on a German network.
  Other models and regions may use different endpoints.
- **No exact firmware build recorded.** The original audit did not record
  the exact webOS/firmware build. Include yours in contributions so the
  list can correlate changes over time.
- **Exact-name semantics.** `-domains.txt` and `-hosts.txt` block exact
  names only — no subdomain coverage. Use `-adblock.txt` for zone coverage
  (see [Format semantics](../README.md#format-semantics)).
- **Region endpoints are enumerated only where observed.** If your region's
  endpoint is missing, it wasn't seen in the audit — submit it.
