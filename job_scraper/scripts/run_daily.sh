#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_daily.sh — Run the LinkedIn job scraper locally.
#
# Usage:
#   ./scripts/run_daily.sh                  # daily incremental scrape (past 24h)
#   ./scripts/run_daily.sh --headed         # visible browser (for debugging)
#   ./scripts/run_daily.sh --sleep-after    # put the Mac to sleep when done
#   ./scripts/run_daily.sh --skip-if-recent # no-op if a run already succeeded today
#
# The scrape runs under `caffeinate` so idle sleep can't tear the browser down
# mid-run. `--sleep-after` returns the Mac to sleep once the run + upload finish.
# `--skip-if-recent` makes the job idempotent-per-day: launchd fires it at several
# times (so some fire while the Mac is awake even if the overnight wake was
# suppressed on battery), and this guard ensures only the first success does work.
#
# Scheduled via launchd: see infra/linkedin-scraper.plist.example
# ---------------------------------------------------------------------------

set -euo pipefail

# Pull our own flags out of the args before forwarding the rest to python
# (main.py uses argparse and would reject an unknown flag).
SLEEP_AFTER=0
SKIP_IF_RECENT=0
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --sleep-after)    SLEEP_AFTER=1 ;;
        --skip-if-recent) SKIP_IF_RECENT=1 ;;
        *)                ARGS+=("$arg") ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"   # job_scraper/ — component-owned logs/.env
REPO_DIR="$(dirname "$PROJECT_DIR")"     # repo root — shared .venv
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "===== LinkedIn scraper started at $(date -u '+%Y-%m-%d %H:%M:%S UTC') ====="

# Catch-up guard: skip if a run already succeeded in the last 20h. Lets launchd
# fire at several times/day (so one lands while the Mac is awake) without
# re-scraping once the day's run is done.
if [[ "$SKIP_IF_RECENT" -eq 1 ]]; then
    DB="$REPO_DIR/data/jobs.db"
    if [[ -f "$DB" ]]; then
        # datetime(started_at) normalizes the stored ISO-8601 'T'/offset form so it
        # compares correctly against datetime('now',...); a raw string compare was
        # wrong ('T' > ' ' made same-date rows always look "recent" -> over-skip ~2d).
        recent=$(sqlite3 "$DB" "SELECT COUNT(*) FROM runs WHERE status='ok' AND datetime(started_at) >= datetime('now','-20 hours')" 2>/dev/null || echo 0)
        if [[ "${recent:-0}" -gt 0 ]]; then
            echo "===== Skipping: a run already succeeded in the last 20h ====="
            exit 0
        fi
    fi
fi

VENV="$REPO_DIR/.venv"                    # one shared virtualenv for the repo
if [[ -d "$VENV" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi

ENV_FILE="$PROJECT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi

cd "$PROJECT_DIR"
# `caffeinate -is` holds idle- AND system-sleep assertions for the scrape's
# lifetime (released when python exits): -i stops idle sleep (battery + AC); -s
# stops system/lid-close sleep but only on AC — macOS forces clamshell sleep on
# battery regardless, so overnight runs still need the laptop plugged in. Without
# -s, closing the lid mid-run suspended the scrape (ballooned wall-clock, no
# clean finish).
# `|| EXIT_CODE=$?` keeps set -e from aborting before the footer logs on failure.
EXIT_CODE=0
caffeinate -is python3 src/main.py scrape ${ARGS[@]+"${ARGS[@]}"} || EXIT_CODE=$?

echo "===== Scraper finished at $(date -u '+%Y-%m-%d %H:%M:%S UTC') (exit $EXIT_CODE) ====="

if [[ "$SLEEP_AFTER" -eq 1 ]]; then
    echo "Returning to sleep (pmset sleepnow)."
    pmset sleepnow || true
fi

exit $EXIT_CODE
