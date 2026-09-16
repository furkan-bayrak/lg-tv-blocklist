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
# Behaviour: tries each URL (2 rounds worst case, 10s cap per attempt => <= ~65s total),
# parses the RFC1123 GMT date, sets the clock, logs OK/WARN to /tmp/webosbrew_hook.log,
# never blocks boot, always exits 0. Idempotent: skips when the clock is already within
# 600s of the fetched time.
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
TOLERANCE=600

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
    [ -n "$dy" ] && [ -n "$hh" ] && [ -n "$mi" ] && [ -n "$ss" ] || return 1
    [ "$yr" -ge 2020 ] && [ "$yr" -le 2100 ] || return 1
    # days-from-civil (Hinnant); all intermediates stay < 2^31
    a=$(( (14 - mo) / 12 ))
    y=$(( yr + 4800 - a ))
    m=$(( mo + 12 * a - 3 ))
    jdn=$(( dy + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045 ))
    days=$(( jdn - 2440588 ))
    echo $(( days * 86400 + hh * 3600 + mi * 60 + ss ))
}

now=$(date +%s)
attempt=0
round=0
while [ $round -lt 2 ]; do
    round=$(( round + 1 ))
    for url in $URLS; do
        attempt=$(( attempt + 1 ))
        hdr=$(curl -sS -D - -o /dev/null --max-time 10 "$url" 2>/dev/null | tr -d '\r' | grep -i '^Date:' | head -n 1)
        [ -n "$hdr" ] || continue
        fetched=$(parse_epoch "$hdr") || continue
        [ -n "$fetched" ] || continue
        drift=$(( fetched - now ))
        [ $drift -lt 0 ] && drift=$(( 0 - drift ))
        if [ $drift -le $TOLERANCE ]; then
            log "OK: clock already within ${drift}s of $url time - skip"
            exit 0
        fi
        localstr=$(date -d "@$fetched" +'%Y-%m-%d %H:%M:%S' 2>/dev/null)
        if [ -n "$localstr" ] && date -s "$localstr" >/dev/null 2>&1; then
            log "OK: clock synced via $url (was off by ${drift}s; set ${localstr} local)"
            exit 0
        fi
    done
done

log "WARN: clock sync failed - no usable Date header from any URL (${attempt} attempts)"
exit 0
