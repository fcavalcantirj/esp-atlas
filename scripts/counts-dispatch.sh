#!/usr/bin/env bash
# esp-atlas — host-timer dispatcher for the hourly GitHub counts workflow.
#
# GitHub's own `on.schedule` dropped most hourly slots (2026-11-07/08: 1 run in 6). An operator-run
# OS timer (systemd, minute 07 UTC) invokes this script instead; it asks GitHub to run the SAME
# workflow (`workflow_dispatch`, publish=true) and records what happened. The collector, the Git
# JSON on branch `runtime-popularity`, the reader and the workflow's concurrency group are unchanged.
#
# One invocation = at most ONE dispatch and exactly ONE receipt line (JSON) appended to
# $COUNTS_RECEIPTS, also printed on stdout, so a silent hour cannot exist. Three overlap guards:
# this script's non-blocking lock (exit 75, nothing ran), a skip when a run of the workflow is
# already queued/in progress, and the workflow's own concurrency group.
#
# Credentials: none here. `gh` uses the host's existing login (needs the `repo` scope for
# workflow_dispatch). This repo is public: no host names, users or paths live in this file —
# the unit file that calls it supplies them through the environment below.
#
# Env (all optional):
#   COUNTS_REPO           owner/repo                      (default fcavalcantirj/esp-atlas)
#   COUNTS_WORKFLOW       workflow file                   (default runtime-popularity.yml)
#   COUNTS_REF            branch whose workflow runs      (default main)
#   COUNTS_SOURCE         run label, becomes the run-name "counts (<source>)" (default host-timer;
#                         a hand-run test MUST say manual-testing so it is never read as automation)
#   COUNTS_STATE_DIR      lock + receipts dir             (default $XDG_STATE_HOME/esp-atlas-counts)
#   COUNTS_LOCK           lock file                       (default $COUNTS_STATE_DIR/dispatch.lock)
#   COUNTS_RECEIPTS       JSONL receipts                  (default $COUNTS_STATE_DIR/receipts.jsonl)
#   COUNTS_SNAPSHOT_URL   published JSON to read back     (default the raw runtime-popularity URL)
#   COUNTS_GH_TIMEOUT     seconds per gh/curl call        (default 60)
#   COUNTS_FIND_SECONDS   wait for the run to appear      (default 60)
#   COUNTS_WAIT_SECONDS   wait for the run to complete    (default 330; the workflow caps at 5 min)
#   COUNTS_POLL_SECONDS   poll interval                   (default 5)
#
# Exit: 0 dispatched and succeeded, or skipped (a run was active) · 1 the dispatch itself failed ·
#       2 the run never appeared, failed, or was still running at the wait bound · 75 lock held.
set -euo pipefail

REPO="${COUNTS_REPO:-fcavalcantirj/esp-atlas}"
WORKFLOW="${COUNTS_WORKFLOW:-runtime-popularity.yml}"
REF="${COUNTS_REF:-main}"
SOURCE="${COUNTS_SOURCE:-host-timer}"
STATE_DIR="${COUNTS_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/esp-atlas-counts}"
LOCK="${COUNTS_LOCK:-$STATE_DIR/dispatch.lock}"
RECEIPTS="${COUNTS_RECEIPTS:-$STATE_DIR/receipts.jsonl}"
SNAPSHOT_URL="${COUNTS_SNAPSHOT_URL:-https://raw.githubusercontent.com/${REPO}/runtime-popularity/popularity.json}"
GH_TIMEOUT="${COUNTS_GH_TIMEOUT:-60}"
FIND_SECONDS="${COUNTS_FIND_SECONDS:-60}"
WAIT_SECONDS="${COUNTS_WAIT_SECONDS:-330}"
POLL_SECONDS="${COUNTS_POLL_SECONDS:-5}"
RUN_NAME="counts (${SOURCE})"

mkdir -p "$STATE_DIR"

# Re-exec under the lock once; a held lock is exit 75 (EX_TEMPFAIL) with nothing run.
if [ -z "${COUNTS_LOCKED:-}" ]; then
  COUNTS_LOCKED=1 exec flock -n -E 75 "$LOCK" "$0" "$@"
fi

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
gh_() { timeout -k 5 "$GH_TIMEOUT" gh "$@"; }

DISPATCHED_AT=""
RUN_ID=null
RUN_CREATED=null
STATUS=""
ACTIVE_RUN_ID=null
DATA_SHA=null
PUBLISHED_AT=null
EXIT=0

receipt() {
  # Exactly one JSON line per invocation: appended to the receipts file and echoed to stdout.
  local line
  line=$(jq -cn \
    --arg dispatched_at "${DISPATCHED_AT:-$(now_utc)}" --arg source "$SOURCE" --arg status "$STATUS" \
    --arg repo "$REPO" --arg workflow "$WORKFLOW" --arg ref "$REF" \
    --argjson run_id "$RUN_ID" --argjson run_created_at "$RUN_CREATED" --argjson active_run_id "$ACTIVE_RUN_ID" \
    --argjson data_sha "$DATA_SHA" --argjson published_at "$PUBLISHED_AT" --argjson exit "$EXIT" \
    '{dispatched_at:$dispatched_at, source:$source, status:$status, repo:$repo, workflow:$workflow, ref:$ref,
      run_id:$run_id, run_created_at:$run_created_at, active_run_id:$active_run_id,
      data_sha:$data_sha, published_at:$published_at, exit:$exit}')
  printf '%s\n' "$line" >> "$RECEIPTS"
  printf '%s\n' "$line"
}

finish() { receipt; exit "$EXIT"; }

# 1. Never stack a second run behind one that is still queued or running.
for st in queued in_progress; do
  active=$(gh_ run list --repo "$REPO" --workflow "$WORKFLOW" --status "$st" --limit 1 \
             --json databaseId,status 2>/dev/null || echo '[]')
  id=$(printf '%s' "$active" | jq -r '.[0].databaseId // empty')
  if [ -n "$id" ]; then
    ACTIVE_RUN_ID="$id"; STATUS="skipped_active"; EXIT=0
    finish
  fi
done

# 2. The dispatch itself.
DISPATCHED_AT=$(now_utc)
if ! gh_ workflow run "$WORKFLOW" --repo "$REPO" --ref "$REF" -f publish=true -f "source=${SOURCE}"; then
  STATUS="dispatch_failed"; EXIT=1
  finish
fi

# 3. Find OUR run: event workflow_dispatch, created at/after the dispatch, run-name = "counts (<source>)".
deadline=$(( $(date +%s) + FIND_SECONDS ))
while :; do
  found=$(gh_ run list --repo "$REPO" --workflow "$WORKFLOW" --event workflow_dispatch \
            --created ">=${DISPATCHED_AT}" --limit 10 \
            --json databaseId,createdAt,displayTitle,status,conclusion 2>/dev/null || echo '[]')
  RUN_ID=$(printf '%s' "$found" | jq -r --arg t "$DISPATCHED_AT" --arg n "$RUN_NAME" \
            '[.[] | select(.displayTitle == $n and .createdAt >= $t)] | sort_by(.createdAt) | .[0].databaseId // "null"')
  if [ "$RUN_ID" != "null" ]; then
    RUN_CREATED=$(printf '%s' "$found" | jq -c --argjson id "$RUN_ID" '.[] | select(.databaseId == $id) | .createdAt')
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    STATUS="run_not_found"; EXIT=2
    finish
  fi
  sleep "$POLL_SECONDS"
done

# 4. Wait, bounded, for the run to complete.
deadline=$(( $(date +%s) + WAIT_SECONDS ))
while :; do
  view=$(gh_ run view "$RUN_ID" --repo "$REPO" --json status,conclusion 2>/dev/null || echo '{}')
  state=$(printf '%s' "$view" | jq -r '.status // ""')
  if [ "$state" = "completed" ]; then
    STATUS=$(printf '%s' "$view" | jq -r '.conclusion // "unknown"')
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    STATUS="wait_timed_out"; EXIT=2
    finish
  fi
  sleep "$POLL_SECONDS"
done
[ "$STATUS" = "success" ] || EXIT=2

# 5. Read back what is now published (best effort; a readback failure leaves nulls, never hides the run).
sha=$(gh_ api "repos/${REPO}/branches/runtime-popularity" -q .commit.sha 2>/dev/null || true)
[ -n "$sha" ] && DATA_SHA=$(jq -cn --arg s "$sha" '$s')
case "$SNAPSHOT_URL" in
  http*) url="${SNAPSHOT_URL}?nocache=$(date +%s)" ;;
  *)     url="$SNAPSHOT_URL" ;;
esac
pub=$(timeout -k 5 "$GH_TIMEOUT" curl -fsS --max-time "$GH_TIMEOUT" "$url" 2>/dev/null | jq -c '.published_at // empty' 2>/dev/null || true)
[ -n "$pub" ] && PUBLISHED_AT="$pub"

finish
