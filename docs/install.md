# Install guide

Step-by-step install for each supported blocker, plus the checks that tell you
it is actually working, the update rules, and the uninstall steps. Pick your
tier in the [README](../README.md#which-list-should-i-use) first. The raw URLs
below always serve the current version.

## Pi-hole (v6)

1. Open the Pi-hole admin page and go to **Lists** in the left menu.
2. Paste the raw URL for your tier into the address field:
   - SAFE: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt`
   - STRICT: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt`
3. Add a comment (for example `LG TV blocklist`) and click **Add blocklist**
   (not Add allowlist).
4. Gravity has not run yet, so the list is not enforced: go to
   **Tools → Update Gravity** and click **Update**, or run `pihole -g` on the
   Pi. Done.

Pi-hole re-downloads subscribed lists on its gravity schedule (weekly by
default), so the list stays current on its own.

**Optional: regex rules.** The `-domains.txt` list is exact-name, so regional
coverage depends on which prefixes were audited. The two regex files generalise
the audited two-letter region families. They supplement exact-name coverage
(`de.`, `us.`, `ca.`, `au.`, `ae.`); STRICT also includes whole-family rules.
They are not adlists: add the lines via **Domains → Add domain** (type **Regex**) or
`pihole --regex '<line>'`. An adlist silently ignores them. When they help and
what they widen: [region FAQ](faq.md#im-not-in-germany--do-the-lists-still-work-for-me).

## AdGuard Home

1. Go to **Filters → DNS blocklists**.
2. Click **Add blocklist → Add a custom list**.
3. Name it `LG TV blocklist` and paste the raw adblock URL for your tier:
   - SAFE: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt`
   - STRICT: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt`
4. Click **Save**. AdGuard Home refreshes subscribed lists on its own update
   interval (24 hours by default).

**Optional: regex rules.** The wildcard files work in AdGuard Home as custom
filtering rules: wrap each line in slashes, for example
`/^[a-z][a-z]\.info\.lgsmartad\.com$/`, and add it under **Filters → Custom
filtering rules**. When they help is covered in the [region
FAQ](faq.md#im-not-in-germany--do-the-lists-still-work-for-me).

## dnsmasq

The dnsmasq files are dnsmasq config snippets: every rule is a complete
`address=/<domain>/#` line, and dnsmasq reads the `#` header lines as
comments. The `#` rule target is not a comment. No conversion step.
Use a dnsmasq build accepting this syntax; see the
[official manual](https://dnsmasq.org/docs/dnsmasq-man.html).

1. Download the raw file for your tier to a staging location outside the
   live configuration directory:
   - SAFE: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-dnsmasq.txt`
   - STRICT: `https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-dnsmasq.txt`
2. Before replacing live router configuration, syntax-check the staged
   snippet with `dnsmasq --test --conf-file=/path/to/staged-lg-tv.conf`.
   Use the router's full-configuration validation as well: a snippet-only
   check cannot check interactions with other configuration. Keep the live
   file unchanged if validation fails. Syntax checks do not start a resolver
   or establish TV compatibility.
3. After the checks pass, save it where dnsmasq reads config (for example
   `/etc/dnsmasq.d/lg-tv-safe.conf` on a router or Pi). Use the router's
   existing include mechanism or a `conf-file` line pointing at it, not both.
4. Reload: `service dnsmasq restart` (or the equivalent on your router).

Check the download against [SHA256SUMS](../lists/SHA256SUMS)
(`sha256sum -c SHA256SUMS` from a full checkout of the repo; compare the
single line for your file if you keep only one list).

`address=/name/#` answers null `0.0.0.0` for A and `::` for AAAA queries
for the name **and every subdomain**, the same matching reach as adblock
`||name^`. This changes answer-family coverage, not list membership or
descendant scope. STRICT's anchored families are therefore region-complete
here too, and its zone anchors (`address=/lge.com/#`, ...) are whole-zone
blocks by nature; for exact-host blocking use `-domains.txt` or `-hosts.txt`
instead. Hosts output still contains only IPv4 mappings. Read the
[store carve-out](faq.md#i-want-strict-but-keep-the-lg-content-store) before
installing STRICT.

**Replace older downloads:** `address=/name/0.0.0.0` snippets retain their
IPv4 limitation; AAAA can be forwarded upstream on dnsmasq 2.86 and later.
Download the new snippet, syntax-check before replacing the live copy, and
reload dnsmasq. Closing this gap can disable features that previously
escaped over IPv6; it is not a new compatibility guarantee.

**Separate query-path limitation:** dual-stack answers only apply when the
query reaches this resolver. IPv6 DNS transport can bypass an IPv4-only
redirect, and DoH can bypass ordinary DNS filtering. See the
[IPv6 DNS-egress caveat](faq.md#can-ipv6-bypass-my-blocklist).
The diagnostic scripts below remain A-only.

## NextDNS

NextDNS has no custom list URLs (third-party lists reach it only through its
curated directory), and the web UI denylist field takes one domain per entry.
Two practical paths:

- **Whole families:** add a zone anchor itself as a denylist entry, for
  example `lgtvcommon.com`. Every subdomain is blocked with it, including
  hosts we have never audited: the same widening STRICT documents. Read
  [keeping the Content
  Store](faq.md#i-want-strict-but-keep-the-lg-content-store) before adding one.
- **The full list:** run [`scripts/nextdns_sync.py`](../scripts/nextdns_sync.py)
  from a clone of this repo. It accepts the generated domains, hosts, adblock
  and single-domain dnsmasq formats, not regex files. It bulk-adds missing
  names to your profile's denylist through the NextDNS API. It dry-runs by
  default and only writes with `--apply`; the API key goes in the
  `NEXTDNS_API_KEY` environment variable. Use `--no-fetch` for an entirely
  offline preview. Run it with `--help` for the profile and file options.

## Unbound (and similar resolvers)

Unbound cannot read a domains file directly; each name needs a `local-data`
entry. From a clone of this repo, convert the list and include the result:

```sh
awk '!/^#/ && NF { print "local-data: \"" $1 " A 0.0.0.0\"" }' \
  lists/safe-domains.txt > /etc/unbound/lg-tv.conf
```

Add `include: "/etc/unbound/lg-tv.conf"` to `unbound.conf` and reload. The
recipe above covers IPv4; add an `AAAA ::` line per name for IPv6 too.

**Do not convert the lists with `local-zone: "name" always_nxdomain`.** That
blocks the whole subtree under each name, which turns every exact-name entry
into a whole-family block. Whole-family blocking is the STRICT philosophy and
belongs in the `src/zones.txt` anchors; use those deliberately, with the
[carve-out](faq.md#i-want-strict-but-keep-the-lg-content-store) in hand.
Format details: [CONTRIBUTING](../CONTRIBUTING.md#format-semantics).

## After install

1. **Make the device query again.** The TV caches DNS answers, so it can keep
   using old ones for a while. Reboot the TV, or toggle its network connection
   (Wi-Fi off, then on). Testing from a computer: flush its cache too, Windows
   `ipconfig /flushdns`, macOS `sudo dscacheutil -flushcache; sudo killall -HUP
   mDNSResponder`, Linux `resolvectl flush-caches`.
2. **Confirm the queries arrive.** Open your blocker's query log and filter by
   the TV's IP address. Open an app on the TV; new rows should appear within
   seconds.
3. **No TV rows at all?** The TV is not using your resolver. That is the
   hardcoded-resolver bypass from [caveat 1](../README.md#the-two-caveats), not
   a broken list; a DNS blocker cannot filter queries it never sees. Fix the
   path at the router, or use the [DNS-egress hook](../examples/webos-hooks/).
4. **Confirm blocking works.** Run the canary check below.

## Is it actually blocking?

Pick a candidate below, then first confirm a **fresh external A answer**
through independent DoH, not your filtering resolver:

```sh
curl -fsS 'https://dns.google/resolve?name=eic.lgtviot.com&type=A'
```

Require Status 0 with a real type-1 A address (follow a CNAME if needed).
NOERROR alone, no-A and NXDOMAIN are not suitable blocking canaries.
The names below were checked on 2026-09-16, not guaranteed live today.
Then query your selected resolver and a control:

| Canary | Tier | Expected answer |
|---|---|---|
| `eic.lgtviot.com` | SAFE | blocked: sinkhole (`0.0.0.0` / `::`) or NXDOMAIN, depending on the blocker |
| `eic.wiseconfig.lgtvcommon.com` | SAFE | blocked: same |
| `snu.lge.com` | STRICT | blocked: same |
| `example.com` | control | a real public IP, proving the resolver still answers |

```sh
nslookup eic.lgtviot.com 192.168.1.53
dig +short eic.lgtviot.com @192.168.1.53
```

If the externally address-resolving canary is locally sinkholed or NXDOMAIN
while the control resolves, that supports A-record blocking **at that
resolver**. It does not prove the TV uses it or that AAAA is blocked.
Confirm new TV queries in your blocker's log separately.

Historical NXDOMAIN annotations are dated snapshots, not permanent retirement
claims. Such names prove nothing about blocking without a fresh external
address. A public local answer can indicate an unenforced rule or bypass;
check the queried resolver and TV routing before drawing a conclusion.

Prefer a script? [`scripts/check_blocking.py`](../scripts/check_blocking.py)
checks IPv4 A-record answers at your selected resolver and cross-checks
negative/sinkhole answers over DoH. An external NXDOMAIN supports DEAD;
NOERROR without an A record is inconclusive, not proof of retirement.
This does not check AAAA filtering, the TV's routing or its DNS cache.

[`scripts/verify.py`](../scripts/verify.py) checks external A-record answers,
not blocking or service purpose. With `--cross-check`, it attempts a second
provider only for non-LIVE findings. NO_A means NOERROR without an A record;
review evidence before changing a rule, including when a name returns NXDOMAIN.

## Keeping the lists up to date

| Item | How it refreshes |
|---|---|
| Pi-hole adlist | Automatically, on the gravity schedule; `pihole -g` forces a re-download |
| AdGuard Home blocklist | Automatically, on the list update interval (24 h default) |
| dnsmasq `conf-file` | Manual: re-download the file and reload dnsmasq after a list update |
| Regex wildcard lines | Manual: they are pasted rules, not a subscription. Re-paste when the file's `# Updated:` header is newer than your paste |
| NextDNS denylist | Manual: re-run `scripts/nextdns_sync.py` after a list update |
| `lists-regions/<cc>/` | Manual: re-run `localize.py` after every list update; the output does not refresh itself |
| Rooted `/etc/hosts` copy | Manual: copy the current `-hosts.txt` again wherever you keep it (the TV copy resets on reboot) |

Every list file starts with `# Updated:` and `# Entries:` headers, so you can
always tell how old the copy you are looking at is.

## Uninstall

- **Pi-hole:** **Lists** → delete the list → **Tools → Update Gravity** again
  (`pihole -g`).
- **AdGuard Home:** **Filters → DNS blocklists** → delete the list; remove any
  custom filtering rules you added.
- **dnsmasq:** remove the `conf-file` line (and the copied list file), then
  reload dnsmasq.
- **NextDNS:** delete the denylist entries in the web UI, one at a time. The
  sync script only adds entries, it never removes them.
- **Unbound:** remove the generated include file and its `include:` line, then
  reload.
- Reboot the TV or toggle its network afterwards, or it keeps using cached
  answers.
