#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# install_daily_trigger.sh — install (or refresh) the launchd job that runs the
#                            scraper at 03:00 daily.
#
# Renders infra/linkedin-scraper.plist.example with this checkout's real path,
# installs it to ~/Library/LaunchAgents, removes any older copy, and (re)loads
# it. Idempotent — safe to run again after pulling changes to the template or
# run_daily.sh. Runs as your normal user; NO sudo (LaunchAgents load in your
# GUI session, not as root).
#
# This is only the "when awake, run the job" half. launchd does NOT wake a
# sleeping Mac — install the daily wake once, separately:
#     sudo ./scripts/setup_wake_schedule.sh
#
# Usage:
#     ./scripts/install_daily_trigger.sh
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_DIR/infra/linkedin-scraper.plist.example"
AGENTS="$HOME/Library/LaunchAgents"
LABEL="com.$(id -un).linkedin-scraper"
DEST="$AGENTS/$LABEL.plist"
UID_NUM="$(id -u)"

mkdir -p "$AGENTS"

# Remove any existing linkedin-scraper agent (incl. a stale label from an
# earlier install) so we never end up with two jobs firing.
for old in "$AGENTS"/*linkedin-scraper*.plist; do
    [[ -e "$old" ]] || continue
    old_label="$(basename "$old" .plist)"
    launchctl bootout "gui/$UID_NUM/$old_label" 2>/dev/null || true
    rm -f "$old"
    echo "removed old agent: $old_label"
done

# Render the template with this checkout's real path + a per-user label.
sed -e "s#/path/to/ds_jobs#$PROJECT_DIR#g" \
    -e "s#com\.user\.linkedin-scraper#$LABEL#g" \
    "$TEMPLATE" > "$DEST"

launchctl bootstrap "gui/$UID_NUM" "$DEST"
echo "installed + loaded: $DEST"
echo

launchctl print "gui/$UID_NUM/$LABEL" 2>/dev/null | grep -E "state =|program =|--sleep-after" || true
echo
echo "Next (one time, needs sudo — the piece launchd can't do):"
echo "    sudo $SCRIPT_DIR/setup_wake_schedule.sh    # wakes the Mac at 02:58 so the 03:00 job can run while asleep"
echo "Verify the wake with:  pmset -g sched"
