#!/usr/bin/env bash
# EspAtlas Jr — daily demand-mine entrypoint (F2). NOT registered by this repo: the owner adds the
# cron job.
#
# Runs jr/demand_run.py from Jr's own clone under a lock and a hard timeout. The runner takes a
# fresh worktree of origin/main, runs THAT worktree's read-only miner (jr/demand.py) with the
# composio interpreter, and lands docs/demand/<date>.json + docs/demand/unresolved.json through
# the tick's PR path (jr/publish.py: protection + earned-trust auto-merge) on a jr/demand-* branch —
# or does nothing when demand is unchanged. No self-update: the miner's code comes from origin/main
# via the worktree, and the hourly jr-tick.sh keeps this clone fast-forwarded.
#
# Secrets: this repo is public, so no key file path lives here. The cron job sets JR_KEYS_FILE to
# the box-local env file (GH_TOKEN for the bot identity — Jr's own keys, never Hermes'); the miner
# reads ~/.composio.key itself (jr/telemetry.py's pattern).
#
# Env: JR_DEMAND_PYTHON  composio interpreter for the miner (default /home/browbot/.composio-venv/bin/python)
#      JR_PYTHON         interpreter for the runner itself (default python3; needs no composio)
#      JR_DEMAND_LOCK    lock file (default /tmp/jr-demand.lock) · JR_DEMAND_TIMEOUT seconds (default 900)
#
# Exit codes: 0 landed or no-op · 1 aborted (the report line says why) · 75 another run holds the
# lock (nothing ran) · 124 killed by timeout (SIGTERM becomes an abort; -k gives 30 s to remove
# the worktree before SIGKILL).
#
# Usage: scripts/jr-demand.sh [--telegram] [--no-auto-merge]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -n "${JR_KEYS_FILE:-}" ] && [ -f "$JR_KEYS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$JR_KEYS_FILE"
  set +a
fi

export JR_DEMAND_PYTHON="${JR_DEMAND_PYTHON:-/home/browbot/.composio-venv/bin/python}"

LOCK="${JR_DEMAND_LOCK:-/tmp/jr-demand.lock}"
exec flock -n -E 75 "$LOCK" timeout -k 30 "${JR_DEMAND_TIMEOUT:-900}" "${JR_PYTHON:-python3}" jr/demand_run.py "$@"
