#!/bin/sh
# 04-sync-clock - set the TV clock from an HTTP "Date:" header (plain HTTP, port 80).
#
# Why: the RTC resets to 2021-01-01 on cold boot on this TV and LG's SDP
# time-sync endpoints are filtered by the DNS stack; with a wrong clock every
# strict-TLS fetch fails ("certificate is not yet valid"), which breaks e.g.
# the Homebrew Channel repo download (error "(0)"). This is a known side
# effect of blocking LG's time domains - symptom write-up:
# https://github.com/furkan-bayrak/lg-tv-blocklist/blob/main/docs/faq.md#homebrew-channel--https-apps-fail-after-power-loss-or-cold-boot
# HTTPS cannot be used here (a wrong clock breaks certificate validation by design).
#
# Requirements: root (webosbrew / Homebrew Channel) and curl (ships with the
# webosbrew image; no other HTTP client is tried).
# Install WITHOUT the .sh extension - webOS run-parts ignores dotted names:
#   cp 04-sync-clock.sh /var/lib/webosbrew/init.d/04-sync-clock
#   chmod 755 /var/lib/webosbrew/init.d/04-sync-clock
# Test now: sh /var/lib/webosbrew/init.d/04-sync-clock && date
# Rollback: rollback-sync-clock.sh, or rm /var/lib/webosbrew/init.d/04-sync-clock
# (the clock value itself needs no revert).
# License: MIT — see LICENSE-MIT.
#
# Behaviour:
# - Fast path: when the current year is already sane (2024..2100) the hook exits
#   immediately without any network fetch.
# - Otherwise all URLs are fetched in parallel (background curl, <= 4s each); a
#   second parallel round runs only when the first produced no usable header.
#   Worst case added boot time is ~2 x 4s, never one timeout per URL.
# - Parsed RFC1123 GMT dates are range-validated (month 1-12, day 1-31 within
#   the month's real length including leap years, hour 0-23, minute 0-59,
#   second 0-60, year 2024..2100); impossible values are rejected, not
#   silently shifted into a valid-but-wrong time. Logs OK/WARN to
#   /tmp/webosbrew_hook.log, never blocks boot, always exits 0.
# - Corroboration: when two or more sources respond, their times must agree
#   within 120s before the clock is set; a single responder is accepted with a
#   WARNING (cannot be corroborated).
# Test override: SYNC_URLS_OVERRIDE="http://url1/ http://url2/"
#
# BUSYBOX NOTES (verified empirically on this TV, webOS 6.5.3, busybox v1.29.3):
# - `10#NN` arithmetic prefix = fatal syntax error -> only ${v#0} single-strip is used.
# - `printf '%d' 08` misparses leading-zero values (prints 0) -> not used.
# - `date -S EPOCH` is broken (clamps at 2^31-1 and wraps around -> lands in
#   1901) -> `date -s 'YYYY-MM-DD HH:MM:SS'` (local time, DST handled by the
#   system TZ Europe/Berlin) is used instead.
# - `date -d @EPOCH +FMT` works and converts to local time -> used for epoch -> local.

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LOG=/tmp/webosbrew_hook.log

log() { echo "04-sync-clock: $1" >> "$LOG" 2>/dev/null; }

URLS="${SYNC_URLS_OVERRIDE:-http://example.com/ http://connectivitycheck.gstatic.com/generate_204 http://repo.webosbrew.org/}"
PER_ATTEMPT_TIMEOUT=4
ROUNDS=2
WORKDIR=""
cleanup() { [ -n "$WORKDIR" ] && rm -rf "$WORKDIR" 2>/dev/null; return 0; }

# --- fast path: a sane clock needs no network at all -------------------------
year=$(date +%Y 2>/dev/null)
year=${year#0}
case "$year" in
    ''|*[!0-9]*) year=0 ;;
esac
if [ "$year" -ge 2024 ] && [ "$year" -le 2100 ]; then
    log "OK: clock already sane (year $year) - no network fetch"
    exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
    log "WARN: curl not found - clock sync skipped"
    exit 0
fi

parse_epoch() {
    # $1 = 'Date: Wed, 16 Sep 2026 07:34:45 GMT' ; echoes epoch, or nothing on reject.
    # Splitting the header into fields is the parsing here (hence the directive):
    # $4 = month, $3 = day, $5 = year, $6 = HH:MM:SS, $7 = timezone.
    # shellcheck disable=SC2086
    set -- $1
    [ "$7" = "GMT" ] || [ "$7" = "UTC" ] || return 1
    case "$4" in
        Jan) mo=1 ;; Feb) mo=2 ;; Mar) mo=3 ;; Apr) mo=4 ;; May) mo=5 ;; Jun) mo=6 ;;
        Jul) mo=7 ;; Aug) mo=8 ;; Sep) mo=9 ;; Oct) mo=10 ;; Nov) mo=11 ;; Dec) mo=12 ;;
        *) return 1 ;;
    esac
    dy="$3"; yr="$5"; tm="$6"
    case "$dy" in [0-9]|[0-9][0-9]) ;; *) return 1 ;; esac
    case "$yr" in [0-9][0-9][0-9][0-9]) ;; *) return 1 ;; esac
    case "$tm" in [0-9][0-9]:[0-9][0-9]:[0-9][0-9]) ;; *) return 1 ;; esac
    hh="${tm%%:*}"; rest="${tm#*:}"
    mi="${rest%%:*}"; ss="${rest#*:}"
    dy="${dy#0}"; hh="${hh#0}"; mi="${mi#0}"; ss="${ss#0}"
    # Range checks: impossible Date values (00/32/99/...) must be rejected, not
    # silently shifted into a valid-but-wrong time. After the single
    # leading-zero strip every value is plain decimal for test(1) (busybox
    # chokes on 10#NN arithmetic, so no prefix is used).
    [ -n "$dy" ] && [ -n "$hh" ] && [ -n "$mi" ] && [ -n "$ss" ] || return 1
    [ "$dy" -ge 1 ] && [ "$dy" -le 31 ] || return 1
    [ "$hh" -le 23 ] || return 1
    [ "$mi" -le 59 ] || return 1
    [ "$ss" -le 60 ] || return 1
    [ "$yr" -ge 2024 ] && [ "$yr" -le 2100 ] || return 1
    # Calendar validity: the day must exist in its month ("31 Feb" must be
    # rejected, not silently shifted into March). Leap rule: divisible by 4,
    # except centuries not divisible by 400 (so 2100 is not a leap year).
    case "$mo" in
        4|6|9|11) md=30 ;;
        2)
            md=28
            if [ $(( yr % 4 )) -eq 0 ] &&
               { [ $(( yr % 100 )) -ne 0 ] || [ $(( yr % 400 )) -eq 0 ]; }; then
                md=29
            fi
            ;;
        *) md=31 ;;
    esac
    [ "$dy" -le "$md" ] || return 1
    # days-from-civil (Hinnant); all intermediates stay < 2^31
    a=$(( (14 - mo) / 12 ))
    y=$(( yr + 4800 - a ))
    m=$(( mo + 12 * a - 3 ))
    jdn=$(( dy + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045 ))
    days=$(( jdn - 2440588 ))
    echo $(( days * 86400 + hh * 3600 + mi * 60 + ss ))
}

# fetch_round <n>: fetch every URL in parallel; each source that answers with
# a valid Date header writes its epoch to $WORKDIR/<n>-<i>. One round is
# bounded by curl's own --max-time (~<= 4s), so the URL count adds no boot
# time -- the same hard per-operation cap the old synchronous loop relied on,
# paid once per round instead of once per URL. This is a boot hook: every path
# stays bounded and no result file means "no source answered".
fetch_round() {
    i=0
    for url in $URLS; do
        i=$(( i + 1 ))
        (
            hdr=$(curl -sS -D - -o /dev/null --connect-timeout 2 --max-time "$PER_ATTEMPT_TIMEOUT" "$url" 2>/dev/null | tr -d '\r' | grep -i '^Date:' | head -n 1)
            [ -n "$hdr" ] || exit 0
            fetched=$(parse_epoch "$hdr") || exit 0
            [ -n "$fetched" ] || exit 0
            printf '%s\n' "$fetched" > "$WORKDIR/$1-$i"
        ) &
    done
    wait
}

# collect_round <n>: read round <n>'s epochs; sets COUNT, FIRST (first in URL
# order), MIN/MAX and SPREAD (seconds between the extremes).
collect_round() {
    COUNT=0; FIRST=""; MIN=""; MAX=""
    for f in "$WORKDIR/$1"-*; do
        [ -f "$f" ] || continue
        ep=$(cat "$f" 2>/dev/null)
        case "$ep" in ''|*[!0-9]*) continue ;; esac
        COUNT=$(( COUNT + 1 ))
        [ -n "$FIRST" ] || FIRST="$ep"
        if [ -z "$MIN" ] || [ "$ep" -lt "$MIN" ]; then MIN="$ep"; fi
        if [ -z "$MAX" ] || [ "$ep" -gt "$MAX" ]; then MAX="$ep"; fi
    done
    SPREAD=0
    if [ -n "$MIN" ] && [ -n "$MAX" ]; then SPREAD=$(( MAX - MIN )); fi
}

WORKDIR="/tmp/04-sync-clock.$$"
if ! mkdir -p "$WORKDIR" 2>/dev/null; then
    log "WARN: cannot create work dir $WORKDIR - clock sync skipped"
    WORKDIR=""
    exit 0
fi

round=1
while [ "$round" -le "$ROUNDS" ]; do
    fetch_round "$round"
    collect_round "$round"
    [ "$COUNT" -gt 0 ] && break
    round=$(( round + 1 ))
done
cleanup

if [ "$COUNT" -eq 0 ]; then
    log "WARN: clock sync failed - no usable Date header in $ROUNDS parallel rounds"
    exit 0
fi

if [ "$COUNT" -ge 2 ] && [ "$SPREAD" -gt 120 ]; then
    log "WARN: $COUNT sources disagree by ${SPREAD}s (>120s) - clock NOT set (possible tampering)"
    exit 0
fi

if [ "$COUNT" -eq 1 ]; then
    log "WARN: only one source responded - accepting without corroboration"
fi

now=$(date +%s)
drift=$(( FIRST - now ))
[ "$drift" -lt 0 ] && drift=$(( 0 - drift ))
localstr=$(date -d "@$FIRST" +'%Y-%m-%d %H:%M:%S' 2>/dev/null)
if [ -n "$localstr" ] && date -s "$localstr" >/dev/null 2>&1; then
    log "OK: clock synced from ${COUNT} source(s) (spread ${SPREAD}s; was off by ${drift}s; set ${localstr} local)"
    exit 0
fi

log "WARN: parsed a plausible time (${FIRST}) but could not set the clock"
exit 0
