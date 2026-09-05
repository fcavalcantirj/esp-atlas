#!/usr/bin/env bash
# EspAtlas Jr — hourly tick entrypoint (the hermes cron `jr-tick`; created PAUSED in Phase 2,
# unpaused only by the Phase 6 cutover ladder).
#
# Runs jr/tick.py from Jr's OWN clone (the directory this script lives in), under a lock and a
# hard timeout, so two ticks can never overlap and a hung one cannot outlive the hour.
#
# Secrets: this repo is public, so no key file path lives here. The cron job sets JR_KEYS_FILE
# to the box-local env file (GH_TOKEN for the bot identity, REVALIDATE_SECRET, TELEGRAM_*);
# when it is unset the tick runs with whatever the environment already has. Even a `--dry-run`
# needs an authenticated `gh` and a python with the repo's deps (JR_PYTHON, default python3).
#
# Exit codes: 0 tick ok · 1 tick aborted (the report line says why) · 75 another tick holds the
# lock (EX_TEMPFAIL, nothing ran) · 124 killed by timeout (the tick turns SIGTERM into an abort
# and still prints its line; -k gives it 30 s to remove its worktree before SIGKILL).
#
# Usage: scripts/jr-tick.sh [--dry-run] [--no-telegram] [--max-calls N] [--max-seconds S]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -n "${JR_KEYS_FILE:-}" ] && [ -f "$JR_KEYS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$JR_KEYS_FILE"
  set +a
fi

LOCK="${JR_LOCK:-/tmp/jr-tick.lock}"
exec flock -n -E 75 "$LOCK" timeout -k 30 "${JR_TIMEOUT:-600}" "${JR_PYTHON:-python3}" jr/tick.py "$@"
