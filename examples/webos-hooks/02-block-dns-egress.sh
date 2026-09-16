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
# Resolver trust: the DNAT target must be a private (10/8, 172.16/12,
# 192.168/16), loopback (127/8) or link-local (169.254/16) IPv4 address. A
# public target (DHCP-pushed 8.8.8.8, a VPN resolver) would be enshrined as
# the "blocking" resolver while the blocklist is bypassed, so a non-local
# target skips the DNAT rules entirely, logs an ERROR and exits 1. Set
# ALLOW_NON_LOCAL_RESOLVER=1 to allow it deliberately (logs a WARNING); the
# resolver-independent rules (853 DROP, v6 guard) are applied either way.
# IPv6 guard: when ip6tables is usable it applies idempotent v6 DROPs
# (udp/tcp 53+853, ::1 excluded) and logs that v6 DNS egress is blocked;
# otherwise, if a v6 default route exists, it warns that unfiltered IPv6 DNS
# could bypass enforcement.
# CAVEAT: `-C || -A` does NOT reconcile a *changed* rule. If the DNAT target
# is ever edited, delete the stale rule first (first match wins), then re-run.
# IPTABLES / IP6TABLES / LUNA_SEND / ALLOW_NON_LOCAL_RESOLVER may be env
# overrides; resolve bare names via PATH, keep explicit paths as-is (busybox
# installs differ across webOS builds).
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
LOG=/var/log/02-block-dns-egress.log
[ -d /var/log ] || LOG=/tmp/02-block-dns-egress.log
FAIL=0

# Resolver to redirect DNS to, in priority order:
#   1. RESOLVER_IP env override (explicit user intent),
#   2. configured IPv4 DNS (dns1) from connectionmanager/getStatus,
#   3. default-route gateway (fallback - legacy behavior).
# If your TV's init runs before the network is up, hardcode it here instead:
#   RESOLVER_IP=<your-resolver-ip>
RESOLVER_IP="${RESOLVER_IP:-}"
RESOLVER_SOURCE=environment

log() {
    LINE="$(date '+%Y-%m-%d %H:%M:%S') 02-block-dns-egress: $1"
    echo "$LINE"
    logger -t 02-block-dns-egress "$1" 2>/dev/null
    echo "$LINE" >> "$LOG" 2>/dev/null
}

# detect_dns_cm: print the first usable IPv4 DNS server (dns1) reported by
# com.webos.service.connectionmanager/getStatus, else print nothing.
# Disconnected interfaces omit the dns keys entirely; IPv6 values and 0.0.0.0
# are skipped (invalid iptables DNAT targets). awk split() on '"' keeps the
# boot path free of extra tooling (no jq); the timeout guard keeps a stuck
# Luna call from hanging init - on failure the gateway fallback applies.
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

# is_local_resolver: true only for IPv4 addresses that can be a LAN-local
# resolver - RFC1918 private, loopback or link-local. Anything else (public,
# CGNAT, malformed) is treated as non-local; the DNAT then skips and, after
# re-verification, the hook still fails loudly. v6 targets are out of scope
# here: the DNAT rules below are IPv4-only.
is_local_resolver() {
    case "$1" in
        10.*|127.*|192.168.*|169.254.*) return 0 ;;
        172.1[6-9].*|172.2[0-9].*|172.3[01].*) return 0 ;;
        *) return 1 ;;
    esac
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

# --- resolver selection: env > configured DNS (connectionmanager) > gateway ---
if [ -z "$RESOLVER_IP" ]; then
    RESOLVER_IP="$(detect_dns_cm)"
    if [ -n "$RESOLVER_IP" ]; then
        RESOLVER_SOURCE="connectionmanager"
    fi
fi
if [ -z "$RESOLVER_IP" ]; then
    RESOLVER_IP="$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')"
    if [ -n "$RESOLVER_IP" ]; then
        RESOLVER_SOURCE="default-route gateway"
    fi
fi
if [ -z "$RESOLVER_IP" ]; then
    log "ERROR: RESOLVER_IP not set and auto-detection failed (connectionmanager + default route) - rules NOT applied"
    exit 1
fi

# --- resolver trust: never enshrine a non-local resolver via DNAT ---
ALLOW_NON_LOCAL_RESOLVER="${ALLOW_NON_LOCAL_RESOLVER:-0}"
APPLY_DNAT=1
if is_local_resolver "$RESOLVER_IP"; then
    log "INFO: resolver: $RESOLVER_IP (source: $RESOLVER_SOURCE)"
elif [ "$ALLOW_NON_LOCAL_RESOLVER" = "1" ]; then
    log "WARNING: resolver $RESOLVER_IP (source: $RESOLVER_SOURCE) is not private/loopback/link-local - continuing because ALLOW_NON_LOCAL_RESOLVER=1"
else
    log "ERROR: refusing DNAT to non-local resolver $RESOLVER_IP (source: $RESOLVER_SOURCE); set ALLOW_NON_LOCAL_RESOLVER=1 if this is intentional"
    APPLY_DNAT=0
    FAIL=1
fi

# --- IPv4 rules (redirect 53, drop DoT/DoQ 853) ---
if [ "$APPLY_DNAT" -eq 1 ]; then
    ensure_v4_nat ! -d 127.0.0.0/8 -p udp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
    ensure_v4_nat ! -d 127.0.0.0/8 -p tcp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
fi
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
elif [ "$APPLY_DNAT" -eq 0 ]; then
    log "ERROR: DNAT refused (non-local resolver) - DNS redirect is NOT active; resolver-independent 853 DROP rules were still applied"
else
    log "ERROR: one or more DNS-egress rules are missing - DNS leak may be open"
fi
exit "$FAIL"
