"""Tests for scripts/counts-dispatch.sh: the host-timer dispatcher of the hourly GitHub counts
workflow, driven against a FAKE `gh` (first on PATH) and a file:// snapshot. No network, no
credentials, no real dispatch.

The dispatcher's contract (DEPLOY.md, "Hourly GitHub counts"):
* a held lock is exit 75 and makes NO gh call (nothing overlaps);
* a queued/in_progress run of the workflow means skip (receipt status skipped_active), no dispatch;
* otherwise exactly ONE `gh workflow run` with publish=true and source=<COUNTS_SOURCE>, the run
  found by its run-name "counts (<source>)", waited to completion, and ONE JSON receipt line with
  run id, conclusion, data-branch sha and published_at;
* a failed dispatch is exit 1 and a run that never appears or fails is exit 2 -- both still write
  the receipt, so a silent hour cannot exist.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

if shutil.which("flock") is None or shutil.which("jq") is None:
    pytest.skip("counts-dispatch.sh needs util-linux flock and jq (the runner and CI have both)",
                allow_module_level=True)

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "counts-dispatch.sh"

FAKE_GH = r'''#!/usr/bin/env bash
# Fake gh: logs argv, answers from $FAKE_GH_DIR. Never touches the network.
set -u
printf '%s\n' "$*" >> "$FAKE_GH_DIR/calls.log"
case "$1 $2" in
  "run list")
    if printf '%s\n' "$@" | grep -qx -- '--status'; then
      cat "$FAKE_GH_DIR/active.json" 2>/dev/null || echo '[]'
    else
      cat "$FAKE_GH_DIR/runs.json" 2>/dev/null || echo '[]'
    fi ;;
  "workflow run")
    exit "$(cat "$FAKE_GH_DIR/dispatch_exit" 2>/dev/null || echo 0)" ;;
  "run view")
    cat "$FAKE_GH_DIR/view.json" ;;
  "api "*)
    cat "$FAKE_GH_DIR/branch_sha" ;;
  *) echo "fake gh: unexpected: $*" >&2; exit 97 ;;
esac
'''


@pytest.fixture
def box(tmp_path):
    """A fake gh on PATH, a scenario dir, a state dir and a file:// snapshot."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    scenario = tmp_path / "gh"
    scenario.mkdir()
    snapshot = tmp_path / "popularity.json"
    snapshot.write_text(json.dumps({"published_at": "2026-11-08T03:07:21Z", "records": {}}))
    state = tmp_path / "state"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_GH_DIR": str(scenario),
        "COUNTS_STATE_DIR": str(state),
        "COUNTS_SOURCE": "test-timer",
        "COUNTS_SNAPSHOT_URL": snapshot.as_uri(),
        "COUNTS_POLL_SECONDS": "0",
        "COUNTS_FIND_SECONDS": "1",
        "COUNTS_WAIT_SECONDS": "1",
    }
    return {"env": env, "scenario": scenario, "state": state, "tmp": tmp_path}


def run(box, **extra):
    env = {**box["env"], **extra}
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)


def calls(box):
    log = box["scenario"] / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def receipts(box):
    path = box["state"] / "receipts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def happy(box, run_id=4242):
    s = box["scenario"]
    (s / "active.json").write_text("[]")
    (s / "runs.json").write_text(json.dumps([
        {"databaseId": 1, "createdAt": "2020-01-01T00:00:00Z", "displayTitle": "counts (test-timer)",
         "status": "completed", "conclusion": "success"},  # old run: must not be picked
        {"databaseId": run_id, "createdAt": "2099-01-01T00:00:00Z", "displayTitle": "counts (test-timer)",
         "status": "in_progress", "conclusion": ""},
        {"databaseId": 7, "createdAt": "2099-01-01T00:00:00Z", "displayTitle": "counts (manual-testing)",
         "status": "completed", "conclusion": "success"},  # other source: must not be picked
    ]))
    (s / "view.json").write_text(json.dumps({"status": "completed", "conclusion": "success"}))
    (s / "branch_sha").write_text("3f9959f1c0ffee00000000000000000000000000\n")


def test_script_is_executable_bash_with_strict_mode():
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    head = SCRIPT.read_text().splitlines()
    assert head[0].startswith("#!/usr/bin/env bash")
    assert any(l.strip().startswith("set -euo pipefail") for l in head[:40])


def test_happy_path_dispatches_once_with_publish_and_source_then_writes_one_receipt(box):
    happy(box)
    r = run(box)
    assert r.returncode == 0, r.stderr
    dispatches = [c for c in calls(box) if c.startswith("workflow run ")]
    assert len(dispatches) == 1
    d = dispatches[0]
    assert "runtime-popularity.yml" in d and "--ref main" in d and "--repo fcavalcantirj/esp-atlas" in d
    assert "publish=true" in d and "source=test-timer" in d
    rec = receipts(box)
    assert len(rec) == 1
    rec = rec[0]
    assert rec["status"] == "success" and rec["run_id"] == 4242 and rec["source"] == "test-timer"
    assert rec["data_sha"] == "3f9959f1c0ffee00000000000000000000000000"
    assert rec["published_at"] == "2026-11-08T03:07:21Z"
    assert rec["exit"] == 0 and rec["dispatched_at"].endswith("Z")
    # the receipt line is also the only thing on stdout (it lands in the unit's append log)
    assert json.loads(r.stdout.strip().splitlines()[-1])["run_id"] == 4242


def test_active_run_means_skip_without_dispatch(box):
    happy(box)
    (box["scenario"] / "active.json").write_text(json.dumps([{"databaseId": 99, "status": "in_progress"}]))
    r = run(box)
    assert r.returncode == 0, r.stderr
    assert not any(c.startswith("workflow run") for c in calls(box))
    rec = receipts(box)
    assert len(rec) == 1 and rec[0]["status"] == "skipped_active" and rec[0]["active_run_id"] == 99


def test_held_lock_is_exit_75_and_no_gh_call(box):
    happy(box)
    box["state"].mkdir()
    lock = box["state"] / "dispatch.lock"
    holder = subprocess.Popen(["flock", str(lock), "sleep", "30"])
    try:
        import time
        time.sleep(0.5)  # let the holder take the lock
        r = run(box)
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 75, (r.stdout, r.stderr)
    assert calls(box) == []
    assert receipts(box) == []


def test_failed_dispatch_is_exit_1_with_a_receipt(box):
    happy(box)
    (box["scenario"] / "dispatch_exit").write_text("1")
    r = run(box)
    assert r.returncode == 1
    rec = receipts(box)
    assert len(rec) == 1 and rec[0]["status"] == "dispatch_failed" and rec[0]["exit"] == 1
    assert rec[0]["run_id"] is None


def test_run_that_never_appears_is_exit_2_with_a_receipt(box):
    happy(box)
    (box["scenario"] / "runs.json").write_text("[]")
    r = run(box)
    assert r.returncode == 2
    rec = receipts(box)
    assert len(rec) == 1 and rec[0]["status"] == "run_not_found" and rec[0]["run_id"] is None


def test_run_that_fails_is_exit_2_with_its_conclusion(box):
    happy(box)
    (box["scenario"] / "view.json").write_text(json.dumps({"status": "completed", "conclusion": "failure"}))
    r = run(box)
    assert r.returncode == 2
    rec = receipts(box)[0]
    assert rec["status"] == "failure" and rec["run_id"] == 4242 and rec["exit"] == 2


def test_run_still_running_at_the_wait_bound_is_exit_2_status_timed_out(box):
    happy(box)
    (box["scenario"] / "view.json").write_text(json.dumps({"status": "in_progress", "conclusion": ""}))
    r = run(box, COUNTS_WAIT_SECONDS="0")
    assert r.returncode == 2
    rec = receipts(box)[0]
    assert rec["status"] == "wait_timed_out" and rec["run_id"] == 4242


def test_receipts_append_and_each_line_is_json(box):
    happy(box)
    assert run(box).returncode == 0
    assert run(box).returncode == 0
    lines = (box["state"] / "receipts.jsonl").read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(l)["run_id"] == 4242 for l in lines)


def test_no_host_identifiers_in_the_script():
    text = SCRIPT.read_text()
    for needle in ("/home/", "browbot", "brownet", "/Users/"):
        assert needle not in text, needle
