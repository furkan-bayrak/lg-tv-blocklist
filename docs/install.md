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
the audited two-letter region prefixes; they are most useful outside `de.`/`us.`/`ca.`
and in STRICT, where they can block whole families on purpose. They are not
adlists: add the lines via **Domains → Add domain** (type **Regex**) or
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
`/^[a-z][a-z]\.nextlgsdp\.com$/`, and add it under **Filters → Custom
filtering rules**. When they help is covered in the [region
FAQ](faq.md#im-not-in-germany--do-the-lists-still-work-for-me).

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
  from a clone of this repo. It bulk-adds the domains from a list file to your
  profile's denylist through the free NextDNS API. It dry-runs by default and
  only writes with `--apply`; the API key goes in the `NEXTDNS_API_KEY`
  environment variable. Run it with `--help` for the profile and file options.

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

Pick a domain from the tier you installed and look it up against your resolver:

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

If the canary is sinkholed or NXDOMAIN while the control resolves, blocking
works for that device. Blocker defaults differ on the block answer (null IP vs
NXDOMAIN); both are fine. The canaries above were live-verified on 2026-09-16.

Two notes. The lists deliberately keep a few dead hosts (annotated
`DECOMMISSIONED` in `src/`); they are NXDOMAIN everywhere and prove nothing, so
always test a live name like the canaries above. And a device that ignores your
DNS shows a normal public IP for the canary; that is the bypass from step 3,
not a list problem.

Prefer a script? [`scripts/check_blocking.py`](../scripts/check_blocking.py)
queries your resolver for a sample of list domains and prints which are
blocked, which are dead, and which still resolve.

## Keeping the lists up to date

| Item | How it refreshes |
|---|---|
| Pi-hole adlist | Automatically, on the gravity schedule; `pihole -g` forces a re-download |
| AdGuard Home blocklist | Automatically, on the list update interval (24 h default) |
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
- **NextDNS:** delete the denylist entries in the web UI, one at a time. The
  sync script only adds entries, it never removes them.
- **Unbound:** remove the generated include file and its `include:` line, then
  reload.
- Reboot the TV or toggle its network afterwards, or it keeps using cached
  answers.
