# Endpoint certificates

Historical TLS measurement snapshot, **2026-09-13**: 62 of 65 endpoints
answered on port 443 with a certificate valid for the queried name.
The then-current source split was 60 STRICT-delta and five SAFE endpoints;
those historical counts are not today's tier inventory. For current source
counts run `python3 scripts/build.py inventory`.

All of it is public data. DNS records are queryable by anyone, and a TLS
certificate is what a server presents to every client that connects. Nothing
here required an LG account, a device, or anything privileged.

## Why this exists

The cluster entries were found by probing, not by watching a TV: the audit ran
in one continent, so the `aic.`/`kic.` twins of its `eic.` hosts were inferred
and then DNS-verified. That raises a fair question — are those names real
services, or just plausible strings that happen to resolve?

These measurements answer an infrastructure question, not all three
[evidence-policy questions](methodology.md#from-data-to-tiers):

| Measurement | Snapshot result | Limit |
|---|---|---|
| DNS A record | 65/65 queried names | Address existence, not TV contact or purpose. |
| TLS endpoint/certificate | 62/65 answered with matching SANs | Endpoint identity at that time, not telemetry purpose, current ownership or compatibility. |
| TV contact / blocking compatibility | Not measured here | Some individually attributed G1 hosts have traffic evidence elsewhere; not every `eic` host was observed. |

A matching certificate does not rule out shared infrastructure, a parked
service, future ownership changes or functional dependencies. Probing a
cluster twin does not inherit the observed sibling's contact or blocking-test
evidence. SAFE promotion requires established purpose and an actual-scope
blocking test, not DNS/TLS identity alone.

## Results

`<cl>` is any of the three clusters.

| Family | Endpoints | Certificate | Issuer |
|---|---|---|---|
| `<cl>.<svc>.lgtvcommon.com` (`ads`, `cdpbeacon`, `cdplauncher`, `homeprv`, `lgchhomeapp`, `nudge`, `recommend`, `service`, `wiseconfig`) | 27 | `*.<svc>.lgtvcommon.com` | Amazon |
| `<cl>-gfts.lge.com`, `<cl>-ngfts.lge.com` | 6 | `*.lge.com` | DigiCert Inc |
| `<cl>-ngfts.nextlgsdp.com`, `<cl>-ngfts.tv.wiselg.com` | 6 | the exact host, per name | Let's Encrypt |
| `<cl>.lgtviot.com`, `<cl>-ocp.lgtviot.com` | 6 | `*.lgtviot.com` | Amazon |
| `<cl>.api.lgtviot.com` | 3 | `*.api.lgtviot.com` | Amazon |
| `<cl>.tv.wiselg.com` | 3 | `*.tv.wiselg.com` | Amazon |
| `<cl>.lgeapi.com` | 3 | `*.lgeapi.com` | Amazon |
| `<cl>.lggalleryplus.com` | 3 | `*.lggalleryplus.com` | Amazon |
| `<cl>-op-lss.lgthinq.com` | 3 | `*.lgthinq.com` | Amazon |
| `<cl>.lgshopsvc.lgappstv.com` | 2 | `*.lgshopsvc.lgappstv.com` | Amazon |
| `<cl>.lgthinq.com` | 3 | **none — see below** | — |

Every certificate matched via `subjectAltName`; none of these families are
CN-only.

## The three that do not answer

In this snapshot, `aic.`, `eic.` and `kic.lgthinq.com` resolved into Azure
ranges but timed out during port-443 handshakes. No certificate was measured
for those three. This establishes neither their current status nor which
port/protocol ThinQ uses; DNS/TLS alone is not device evidence.

## Two absences worth recording

At the snapshot date, `kic.lgshopsvc.lgappstv.com` returned NXDOMAIN on both
providers while the `aic.`/`eic.` candidates resolved. Names were probed
individually, not assumed from a pattern.

Of 18 candidate three-letter prefixes probed then, exactly `eic`, `aic` and
`kic` resolved for these families. This is bounded historical evidence, not
a claim that no other clusters or wildcard records exist today; later
issue #28 includes `ruc` candidates.

## Reproducing this

Resolution goes over DNS-over-HTTPS on purpose. If you run a DNS blocker — and
if you are reading this, you do — a normal lookup returns your own sinkhole for
these exact names, so every endpoint would look dead.

```sh
# 1. resolve over DoH, bypassing any local blocker or port-53 redirect
ip=$(curl -s "https://dns.google/resolve?name=aic.cdpbeacon.lgtvcommon.com&type=A" \
     | grep -oE '"data":"[0-9.]+"' | head -1 | cut -d'"' -f4)

# 2. handshake with that IP, sending SNI, and read the certificate
openssl s_client -connect "$ip:443" -servername aic.cdpbeacon.lgtvcommon.com </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -ext subjectAltName
```

Check the queried name is covered by `subjectAltName`. The DNS half is a plain
DoH query per name, run against a second provider as well before any finding
here is trusted.

## License

[CC BY 4.0](../LICENSE), as with the rest of the list content.
