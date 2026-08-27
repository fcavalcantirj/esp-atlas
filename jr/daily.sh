#!/usr/bin/env bash
# EspAtlas Jr — daily heartbeat wrapper (scheduled via hermes cron / systemd).
# Activates Jr's venv and runs the daily job, which self-nudges Felipe on Telegram.
set -euo pipefail
cd "$(dirname "$0")"
. .venv/bin/activate
exec python run.py daily
