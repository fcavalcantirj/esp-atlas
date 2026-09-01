#!/usr/bin/env bash
# EspAtlas Jr — catalog-drain cron entrypoint (JR.md Law 3: bot proposes, humans dispose).
# Runs the deterministic drain + PR orchestrator (jr/drain_pr.py) and prints its one-line
# summary to stdout. Opens a PR when the drain authored new entries; prints a terse
# no-new-entries line and touches no git state otherwise.
#
# Usage: scripts/jr-drain.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 jr/drain_pr.py
