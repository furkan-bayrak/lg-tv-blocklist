# Endpoint certificates

TLS evidence for the datacentre-cluster entries (`eic.`, `aic.`, `kic.`): does a
live service answer on port 443 with a certificate valid for that exact
hostname? Checked **2026-09-13**: 62 of 65 do.

All of it is public data. DNS records are queryable by anyone, and a TLS
certificate is what a server presents to every client that connects. Nothing
here required an LG account, a device, or anything privileged.

## Why this exists

The cluster entries were found by probing, not by watching a TV: the audit ran
in one continent, so the `aic.`/`kic.` twins of its `eic.` hosts were inferred
and then DNS-verified. That raises a fair question — are those names real
services, or just plausible strings that happen to resolve?

Three grades of evidence, and it is worth being precise about which one any
given entry has:

| Grade | Claim | Cluster entries |
|---|---|---|
| 1. DNS resolves | An A record exists for this name | 65/65 |
| 2. Live LG-controlled TLS service | Something answers on 443 with a certificate LG controls, valid for this name | **62/65 — this document** |
| 3. Traffic observed | A real TV on that continent queried it | the audited `eic.` hosts only |

Grade 2 rules out two things grade 1 cannot: a stale DNS record pointing at
decommissioned infrastructure, and the name being parked or held by a third
party. It does **not** establish grade 3, and nothing here should be read as
claiming it does. Proving that a TV in the Americas contacts
`aic.cdpbeacon.lgtvcommon.com` requires a TV in the Americas — which is why the
`aic.`/`kic.` entries are tagged `weak` in `src/strict.txt` and a querylog from
those regions is the most valuable thing anyone can contribute.

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

`aic.`, `eic.` and `kic.lgthinq.com` resolve — into Azure ranges, unlike every
other family here, which is on AWS — but never complete a handshake on 443: the
connection times out rather than being refused. They stay in the lists as grade
1 only. Nothing here establishes which port or protocol ThinQ's
cluster entry points actually use.

## Two absences worth recording

`kic.lgshopsvc.lgappstv.com` does not exist (NXDOMAIN on both providers) while
`aic.` and `eic.` are live. It is the only asymmetric stem in the set — every
other clustered service is fronted from all three. That is why each cluster name
is probed and listed individually rather than generated from a pattern.

Of 18 candidate three-letter prefixes probed against these families, exactly
`eic`, `aic` and `kic` exist. The rest are NXDOMAIN, so no wildcard record is
making invented names appear to resolve.

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
