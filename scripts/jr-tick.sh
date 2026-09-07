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
# lock (EX_TEMPFAIL, nothing ran) · 76 skipped, SoC too hot (nothing ran) · 124 killed by timeout (the tick turns SIGTERM into an abort
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

# Thermal gate (the Pi runs at its warn line with the fan maxed): when the SoC is above
# JR_MAX_TEMP_MC millidegrees (default 78000 = 78 °C), skip this hour instead of adding load.
# Exit 76 so the scheduler can tell "too hot, nothing ran" from "lock busy" (75) and a real run.
THERMAL="${JR_THERMAL_FILE:-/sys/class/thermal/thermal_zone0/temp}"
if [ -r "$THERMAL" ]; then
  TEMP_MC="$(cat "$THERMAL" 2>/dev/null || echo 0)"
  if [ "${TEMP_MC:-0}" -gt "${JR_MAX_TEMP_MC:-78000}" ] 2>/dev/null; then
    echo "jr-tick: skipped, SoC at $((TEMP_MC / 1000)) °C > $((${JR_MAX_TEMP_MC:-78000} / 1000)) °C" >&2
    exit 76
  fi
fi

# Self-update: the tick's CODE is whatever this clone has checked out (its DATA comes from a
# fresh worktree of origin/main), so a merged fix reached the Pi only when someone pulled.
# Fast-forward to origin/main first, on a clean tree only — never rewrite local work. A
# failed fetch (offline) runs the code we have; JR_NO_SELF_UPDATE=1 pins it for debugging.
if [ -z "${JR_NO_SELF_UPDATE:-}" ] && [ -z "$(git status --porcelain --untracked-files=no)" ]; then
  if git fetch -q origin main; then
    git merge -q --ff-only origin/main || echo "jr-tick: not fast-forwardable to origin/main, running the checked-out code" >&2
  else
    echo "jr-tick: fetch failed, running the checked-out code" >&2
  fi
fi

LOCK="${JR_LOCK:-/tmp/jr-tick.lock}"
exec flock -n -E 75 "$LOCK" timeout -k 30 "${JR_TIMEOUT:-600}" "${JR_PYTHON:-python3}" jr/tick.py "$@"
