#!/bin/sh
# 02-block-dns-egress - force all TV-originated DNS through your own resolver.
#
# What it does: webOS daemons hardcode public resolvers (8.8.8.8 / 1.1.1.1),
# so queries bypass your LAN DNS and your blocklist / AdGuard / Pi-hole rules
# never see them. This hook DNATs all TV-originated DNS (udp/tcp 53) to your
# resolver via the nat-OUTPUT chain and drops DoT/DoQ (udp/tcp 853) at the
# kernel, so your resolver's rules actually apply. Loopback (127.0.0.0/8) is
# excluded so the TV's local DNS stub keeps working.
#
# Requirements: root (webosbrew / Homebrew Channel).
# Install WITHOUT the .sh extension - webOS run-parts ignores dotted names:
#   /var/lib/webosbrew/init.d/02-block-dns-egress
# Rollback: rollback-dns-egress.sh (loops -D), or remove this file from
# /var/lib/webosbrew/init.d and reboot.
# License: MIT — see LICENSE-MIT.
#
# Hardening: after apply, every expected rule is re-verified with `-C`; a
# missing rule logs an ERROR and the hook exits 1 instead of printing success
# unconditionally (a boot-time failure would silently reopen the leak).
# IPv6 guard: when ip6tables is usable it applies idempotent v6 DROPs
# (udp/tcp 53+853, ::1 excluded) and logs that v6 DNS egress is blocked;
# otherwise, if a v6 default route exists, it warns that unfiltered IPv6 DNS
# could bypass enforcement.
# CAVEAT: `-C || -A` does NOT reconcile a *changed* rule. If the DNAT target
# is ever edited, delete the stale rule first (first match wins), then re-run.
# IPTABLES / IP6TABLES may be env overrides; resolve bare names via PATH,
# keep explicit paths as-is (busybox installs differ across webOS builds).
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
LOG=/var/log/02-block-dns-egress.log
[ -d /var/log ] || LOG=/tmp/02-block-dns-egress.log
FAIL=0

# Resolver to redirect DNS to. Empty -> auto-detect from the default route.
# If your TV's init runs before the network is up, hardcode it here instead:
#   RESOLVER_IP=<your-resolver-ip>
RESOLVER_IP="${RESOLVER_IP:-}"

log() {
    LINE="$(date '+%Y-%m-%d %H:%M:%S') 02-block-dns-egress: $1"
    echo "$LINE"
    logger -t 02-block-dns-egress "$1" 2>/dev/null
    echo "$LINE" >> "$LOG" 2>/dev/null
}

# ensure_* : add the rule only if absent (idempotent), then verify with -C.
ensure_v4_nat() {
    if ! "$IPTABLES" -t nat -C OUTPUT "$@" 2>/dev/null; then
        "$IPTABLES" -t nat -A OUTPUT "$@" 2>/dev/null && log "INFO: added nat-OUTPUT rule: $*"
    fi
    "$IPTABLES" -t nat -C OUTPUT "$@" 2>/dev/null || { log "ERROR: nat-OUTPUT rule missing after apply: $*"; FAIL=1; }
}
ensure_v4_out() {
    if ! "$IPTABLES" -C OUTPUT "$@" 2>/dev/null; then
        "$IPTABLES" -A OUTPUT "$@" 2>/dev/null && log "INFO: added OUTPUT rule: $*"
    fi
    "$IPTABLES" -C OUTPUT "$@" 2>/dev/null || { log "ERROR: OUTPUT rule missing after apply: $*"; FAIL=1; }
}
ensure_v6_out() {
    if ! "$IP6TABLES" -C OUTPUT "$@" 2>/dev/null; then
        "$IP6TABLES" -A OUTPUT "$@" 2>/dev/null && log "INFO: added ip6tables OUTPUT rule: $*"
    fi
    "$IP6TABLES" -C OUTPUT "$@" 2>/dev/null || { log "ERROR: ip6tables OUTPUT rule missing after apply: $*"; FAIL=1; }
}

if [ ! -x "$IPTABLES" ]; then
    log "ERROR: $IPTABLES missing or not executable - DNS-egress rules NOT applied (DNS leak open!)"
    exit 1
fi

if [ -z "$RESOLVER_IP" ]; then
    RESOLVER_IP="$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')"
fi
if [ -z "$RESOLVER_IP" ]; then
    log "ERROR: RESOLVER_IP not set and default-route detection failed - rules NOT applied"
    exit 1
fi
log "INFO: resolver: $RESOLVER_IP"

# --- IPv4 rules (redirect 53, drop DoT/DoQ 853) ---
ensure_v4_nat ! -d 127.0.0.0/8 -p udp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
ensure_v4_nat ! -d 127.0.0.0/8 -p tcp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
ensure_v4_out -p tcp --dport 853 -j DROP
ensure_v4_out -p udp --dport 853 -j DROP

# --- IPv6 guard (state-dependent) ---
V6_DEFAULT="$(ip -6 route show default 2>/dev/null | head -n 1)"
if [ -x "$IP6TABLES" ] && "$IP6TABLES" -L -n >/dev/null 2>&1; then
    ensure_v6_out ! -d ::1/128 -p udp --dport 53 -j DROP
    ensure_v6_out ! -d ::1/128 -p tcp --dport 53 -j DROP
    ensure_v6_out ! -d ::1/128 -p udp --dport 853 -j DROP
    ensure_v6_out ! -d ::1/128 -p tcp --dport 853 -j DROP
    log "INFO: IPv6 DNS egress blocked (udp/tcp 53+853 DROP); IPv4 DNS unaffected"
elif [ -n "$V6_DEFAULT" ]; then
    log "WARNING: IPv6 default route present ($V6_DEFAULT), ip6tables unusable (kernel lacks ip6_tables) - IPv6 udp/tcp 53+853 NOT filtered; a future global IPv6 prefix could bypass enforcement"
fi

# --- result: success line only when every expected rule verified present ---
if [ "$FAIL" -eq 0 ]; then
    log "OK: all DNS-egress rules verified active (dnat 53 -> $RESOLVER_IP, drop 853)"
else
    log "ERROR: one or more DNS-egress rules are missing - DNS leak may be open"
fi
exit "$FAIL"
