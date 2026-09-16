#!/bin/sh
# rollback-sync-clock.sh - undo 04-sync-clock.
#
# Removes the clock-sync hook from webosbrew init.d, so future boots no longer
# fetch an HTTP "Date:" header to correct the clock. The current clock value
# is NOT reverted - the hook only ever corrects it, there is no stale value
# worth restoring. Running this script IS the full removal:
#   rm /var/lib/webosbrew/init.d/04-sync-clock
# Post-check: prints the current date and the init.d listing.
# License: MIT — see LICENSE-MIT.
HOOK="${SYNC_CLOCK_HOOK:-/var/lib/webosbrew/init.d/04-sync-clock}"

if [ -e "$HOOK" ]; then
    if rm -f "$HOOK"; then
        echo "removed: $HOOK"
    else
        echo "ERROR: could not remove $HOOK (read-only filesystem?)" >&2
        exit 1
    fi
else
    echo "not installed: $HOOK (nothing to remove)"
fi

echo "--- current clock ---"
date
echo "--- /var/lib/webosbrew/init.d ---"
ls -la /var/lib/webosbrew/init.d/ 2>/dev/null || echo "init.d directory not readable"
echo "Note: the clock stays at its current (corrected) value; nothing else to undo."
