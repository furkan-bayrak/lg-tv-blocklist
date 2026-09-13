#!/bin/sh
# rollback-dns-egress.sh - undo 02-block-dns-egress.
#
# Removes ALL live DNS-egress rules: each -D runs in a loop until it fails,
# so duplicates (if any) are removed too. Prints iptables post-checks at end.
# The DNAT rules are matched by resolver IP: the configured DNS is
# auto-detected via connectionmanager when available, else the default route
# (or pass RESOLVER_IP=... if you hardcoded one in the hook). If your resolver
# changed since install, remove any leftover nat-OUTPUT rule shown in the
# post-check: iptables -t nat -D OUTPUT <line-number>
# Permanent removal: rm /var/lib/webosbrew/init.d/02-block-dns-egress && reboot
# License: MIT — see LICENSE-MIT.
# IPTABLES / IP6TABLES / LUNA_SEND may be env overrides; resolve bare names via
# PATH, keep explicit paths as-is (busybox installs differ across webOS builds).
IPTABLES="${IPTABLES:-iptables}"
case "$IPTABLES" in
    */*) ;;
    *) IPTABLES="$(command -v "$IPTABLES" 2>/dev/null || echo "/usr/sbin/$IPTABLES")" ;;
esac
IP6TABLES="${IP6TABLES:-ip6tables}"
case "$IP6TABLES" in
    */*) ;;
    *) IP6TABLES="$(command -v "$IP6TABLES" 2>/dev/null || echo "/usr/sbin/$IP6TABLES")" ;;
esac
LUNA_SEND="${LUNA_SEND:-luna-send}"
case "$LUNA_SEND" in
    */*) ;;
    *) LUNA_SEND="$(command -v "$LUNA_SEND" 2>/dev/null || echo "/usr/bin/$LUNA_SEND")" ;;
esac
[ -x "$IPTABLES" ] || exit 0

# detect_dns_cm: print the first usable IPv4 DNS server (dns1) reported by
# com.webos.service.connectionmanager/getStatus, else print nothing. Same
# parsing (and priority) as 02-block-dns-egress.sh so the rollback matches
# the exact rule the hook installed.
detect_dns_cm() {
    if command -v timeout >/dev/null 2>&1; then
        LUNA_JSON="$(timeout -t 5 "$LUNA_SEND" -n 1 luna://com.webos.service.connectionmanager/getStatus '{}' 2>/dev/null)"
    else
        LUNA_JSON="$("$LUNA_SEND" -n 1 luna://com.webos.service.connectionmanager/getStatus '{}' 2>/dev/null)"
    fi
    [ -n "$LUNA_JSON" ] || return 0
    printf '%s\n' "$LUNA_JSON" | awk '
        {
            n = split($0, part, "\"")
            for (i = 1; i <= n; i++) {
                if (part[i] == "dns1" && part[i + 1] == ":") {
                    value = part[i + 2]
                    if (value ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && value != "0.0.0.0") {
                        print value
                        exit
                    }
                }
            }
        }'
}

# Resolver matching the hook's live rule, in priority order: RESOLVER_IP env >
# configured DNS (connectionmanager dns1) > default-route gateway.
RESOLVER_IP="${RESOLVER_IP:-}"
if [ -z "$RESOLVER_IP" ]; then
    RESOLVER_IP="$(detect_dns_cm)"
fi
[ -n "$RESOLVER_IP" ] || RESOLVER_IP="$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')"
if [ -n "$RESOLVER_IP" ]; then
    while "$IPTABLES" -t nat -D OUTPUT ! -d 127.0.0.0/8 -p udp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53" 2>/dev/null; do :; done
    while "$IPTABLES" -t nat -D OUTPUT ! -d 127.0.0.0/8 -p tcp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53" 2>/dev/null; do :; done
else
    echo "WARNING: resolver not detected - DNAT rules (if any) not removed; see the nat post-check below"
fi
while "$IPTABLES" -D OUTPUT -p tcp --dport 853 -j DROP 2>/dev/null; do :; done
while "$IPTABLES" -D OUTPUT -p udp --dport 853 -j DROP 2>/dev/null; do :; done

# v6 rules (present only if the hook found a usable ip6tables)
if [ -x "$IP6TABLES" ] && "$IP6TABLES" -L -n >/dev/null 2>&1; then
    while "$IP6TABLES" -D OUTPUT ! -d ::1/128 -p udp --dport 53 -j DROP 2>/dev/null; do :; done
    while "$IP6TABLES" -D OUTPUT ! -d ::1/128 -p tcp --dport 53 -j DROP 2>/dev/null; do :; done
    while "$IP6TABLES" -D OUTPUT ! -d ::1/128 -p udp --dport 853 -j DROP 2>/dev/null; do :; done
    while "$IP6TABLES" -D OUTPUT ! -d ::1/128 -p tcp --dport 853 -j DROP 2>/dev/null; do :; done
    echo "--- ip6tables -S OUTPUT ---"
    "$IP6TABLES" -S OUTPUT
fi

echo "$(date) rollback-dns-egress: rules removed (all duplicates)"
echo "--- iptables -S ---"
"$IPTABLES" -S
echo "--- iptables -t nat -S ---"
"$IPTABLES" -t nat -S
echo "Permanent: rm /var/lib/webosbrew/init.d/02-block-dns-egress && reboot"
