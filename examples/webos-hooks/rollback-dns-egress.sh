#!/bin/sh
# rollback-dns-egress.sh - undo 02-block-dns-egress.
#
# Removes ALL live DNS-egress rules: each -D runs in a loop until it fails,
# so duplicates (if any) are removed too. Prints iptables post-checks at end.
# The DNAT rules are matched by resolver IP: the default route is auto-detected
# (or pass RESOLVER_IP=... if you hardcoded one in the hook). If your gateway
# changed since install, remove any leftover nat-OUTPUT rule shown in the
# post-check: iptables -t nat -D OUTPUT <line-number>
# Permanent removal: rm /var/lib/webosbrew/init.d/02-block-dns-egress && reboot
# License: MIT — see LICENSE-MIT.
IPTABLES="${IPTABLES:-$(command -v iptables 2>/dev/null || echo /usr/sbin/iptables)}"
IPT6=/usr/sbin/ip6tables
[ -x "$IPTABLES" ] || exit 0

RESOLVER_IP="${RESOLVER_IP:-}"
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
if [ -x "$IPT6" ] && $IPT6 -L -n >/dev/null 2>&1; then
    while $IPT6 -D OUTPUT ! -d ::1/128 -p udp --dport 53 -j DROP 2>/dev/null; do :; done
    while $IPT6 -D OUTPUT ! -d ::1/128 -p tcp --dport 53 -j DROP 2>/dev/null; do :; done
    while $IPT6 -D OUTPUT ! -d ::1/128 -p udp --dport 853 -j DROP 2>/dev/null; do :; done
    while $IPT6 -D OUTPUT ! -d ::1/128 -p tcp --dport 853 -j DROP 2>/dev/null; do :; done
    echo "--- ip6tables -S OUTPUT ---"
    $IPT6 -S OUTPUT
fi

echo "$(date) rollback-dns-egress: rules removed (all duplicates)"
echo "--- iptables -S ---"
"$IPTABLES" -S
echo "--- iptables -t nat -S ---"
"$IPTABLES" -t nat -S
echo "Permanent: rm /var/lib/webosbrew/init.d/02-block-dns-egress && reboot"
