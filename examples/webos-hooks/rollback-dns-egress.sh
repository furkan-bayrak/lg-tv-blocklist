#!/bin/sh
# rollback-dns-egress.sh - undo 02-block-dns-egress.
#
# Removes and verifies the targeted OUTPUT rules, including duplicates.
# The DNAT rules are matched by the selected resolver IP. Resolver discovery
# uses the same priority as the apply hook. If your resolver changed since
# install, pass RESOLVER_IP=<old-resolver>; this script only removes DNAT
# rules for the selected address. Prints the inspected OUTPUT chains.
# Unverifiable or incomplete removal exits 1, including unavailable tooling.
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
FAIL=0

# detect_dns_cm: print the first usable IPv4 DNS server (dns1) reported by
# com.webos.service.connectionmanager/getStatus, else print nothing. Same
# parsing (and priority) as 02-block-dns-egress.sh so the rollback matches
# the exact rule the hook installed.
detect_dns_cm() {
    if timeout -t 1 true >/dev/null 2>&1; then
        set -- -t 5
    elif timeout 1 true >/dev/null 2>&1; then
        set -- 5
    else
        echo "WARNING: no usable timeout; skipping connectionmanager DNS discovery" >&2
        return 0
    fi
    LUNA_JSON="$(timeout "$@" "$LUNA_SEND" -n 1 luna://com.webos.service.connectionmanager/getStatus '{}' 2>/dev/null)" || return 0
    [ -n "$LUNA_JSON" ] || return 0
    printf '%s\n' "$LUNA_JSON" | awk '
        { json = json $0 "\n" }
        END {
            n = split(json, part, "\"")
            for (i = 1; i + 2 <= n; i++) {
                if (part[i] == "dns1" && part[i + 1] ~ /^[[:space:]]*:[[:space:]]*$/) {
                    value = part[i + 2]
                    if (value ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && value != "0.0.0.0") {
                        print value
                        exit
                    }
                }
            }
        }'
}

# Match the same dotted-quad format as apply, including explicit public
# overrides that might have been installed with ALLOW_NON_LOCAL_RESOLVER=1.
is_dotted_quad() {
    case "$1" in
        *[!0-9.]*|.*|*.) return 1 ;;
    esac
    old_ifs="$IFS"
    IFS=.
    # shellcheck disable=SC2086
    set -- $1
    IFS="$old_ifs"
    [ $# -eq 4 ] || return 1
    for octet in "$@"; do
        case "$octet" in
            ''|*[!0-9]*|0[0-9]*) return 1 ;;
        esac
        [ "$octet" -le 255 ] || return 1
    done
    return 0
}

inspect_output() {
    if [ -x "$1" ] && "$1" -t "$2" -S OUTPUT 2>/dev/null; then
        return 0
    fi
    echo "WARNING: cannot inspect $1 $2 OUTPUT; rollback unverified" >&2
    FAIL=1
    return 1
}

remove_rule() {
    tool=$1
    table=$2
    shift 2
    while :; do
        check_error=$(LC_ALL=C "$tool" -t "$table" -C OUTPUT "$@" 2>&1 >/dev/null)
        case "$?:${check_error%.}" in
            0:*)
                if ! "$tool" -t "$table" -D OUTPUT "$@" 2>/dev/null; then
                    echo "ERROR: failed to delete $tool $table OUTPUT rule: $*" >&2
                    FAIL=1
                    return
                fi
                ;;
            1:*': Bad rule (does a matching rule exist in that chain?)')
                # Exit 1 also covers operational errors. Accept the explicit
                # absence diagnostic only while the table remains readable.
                inspect_output "$tool" "$table" >/dev/null
                return
                ;;
            *)
                echo "ERROR: cannot verify $tool $table OUTPUT rule: $*" >&2
                [ -z "$check_error" ] || printf '%s\n' "$check_error" >&2
                FAIL=1
                return
                ;;
        esac
    done
}

if inspect_output "$IPTABLES" nat >/dev/null; then
    RESOLVER_IP="${RESOLVER_IP:-}"
    [ -n "$RESOLVER_IP" ] || RESOLVER_IP="$(detect_dns_cm)"
    [ -n "$RESOLVER_IP" ] || RESOLVER_IP="$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')"
    if is_dotted_quad "$RESOLVER_IP"; then
        remove_rule "$IPTABLES" nat ! -d 127.0.0.0/8 -p udp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
        remove_rule "$IPTABLES" nat ! -d 127.0.0.0/8 -p tcp --dport 53 -j DNAT --to-destination "$RESOLVER_IP:53"
    else
        echo "WARNING: no valid IPv4 resolver; DNAT removal unverified (pass RESOLVER_IP=<installed-resolver>)" >&2
        FAIL=1
    fi
    echo "--- iptables -t nat -S OUTPUT ---"
    inspect_output "$IPTABLES" nat
fi

if inspect_output "$IPTABLES" filter >/dev/null; then
    remove_rule "$IPTABLES" filter -p tcp --dport 853 -j DROP
    remove_rule "$IPTABLES" filter -p udp --dport 853 -j DROP
    echo "--- iptables -S OUTPUT ---"
    inspect_output "$IPTABLES" filter
fi

if inspect_output "$IP6TABLES" filter >/dev/null; then
    remove_rule "$IP6TABLES" filter ! -d ::1/128 -p udp --dport 53 -j DROP
    remove_rule "$IP6TABLES" filter ! -d ::1/128 -p tcp --dport 53 -j DROP
    remove_rule "$IP6TABLES" filter ! -d ::1/128 -p udp --dport 853 -j DROP
    remove_rule "$IP6TABLES" filter ! -d ::1/128 -p tcp --dport 853 -j DROP
    echo "--- ip6tables -S OUTPUT ---"
    inspect_output "$IP6TABLES" filter
fi

if [ "$FAIL" -eq 0 ]; then
    echo "OK: targeted DNS-egress rules absent (including duplicates for resolver $RESOLVER_IP)"
else
    echo "ERROR: DNS-egress rollback incomplete or unverified" >&2
fi
echo "For permanent removal, remove the init.d hook and reboot."
exit "$FAIL"
