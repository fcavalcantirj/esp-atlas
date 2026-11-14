"""The tick hands admit's backlog to the stall alarm (jr/admit_progress.py) and sends its nudges to
Telegram on a real run only; the alarm never aborts the tick."""
from __future__ import annotations

from types import SimpleNamespace

import tick
from test_tick import git_ok, gh_ok, run, wt_dir  # noqa: F401


def admit_stage(backlog):
    return lambda ctx: tick.StageResult("admit", summary="backlog 7 undecided; stopped before x/y", backlog=backlog)


def test_the_tick_hands_the_backlog_to_the_watcher(tmp_path):
    seen = []
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), stages=[admit_stage(7)],
            admit_watcher=lambda n, where, now, dry: seen.append((n, dry)) or {"status": "ok", "nudges": []})
    assert seen == [(7, True)] and not r.aborted


def test_a_real_tick_sends_the_stall_nudge(wt_dir):
    sent = []
    run(git=git_ok(wt_dir), gh=gh_ok(), stages=[admit_stage(7)], notifier=sent.append,
        admit_watcher=lambda *a: {"status": "ok", "nudges": ["stalled!"]})
    assert "stalled!" in sent


def test_a_dry_run_sends_no_stall_nudge(tmp_path):
    sent = []
    run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), stages=[admit_stage(7)], notifier=sent.append,
        admit_watcher=lambda *a: {"status": "ok", "nudges": ["stalled!"]})
    assert sent == []


def test_a_failing_watcher_never_aborts_the_tick(tmp_path):
    def boom(*a):
        raise RuntimeError("disk full")
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), stages=[admit_stage(7)], admit_watcher=boom)
    assert not r.aborted and any("admit progress" in w for w in r.warnings)


def test_no_admit_stage_means_no_observation(tmp_path):
    seen = []
    run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), stages=[],
        admit_watcher=lambda *a: seen.append(a) or {"status": "ok", "nudges": []})
    assert seen == []


def test_the_hourly_entry_point_wires_the_real_admit_watcher(monkeypatch):
    got = {}
    monkeypatch.setattr(tick, "run_tick", lambda **kw: got.update(kw) or SimpleNamespace(aborted=None))
    tick.main(["--dry-run", "--no-telegram"])
    assert got.get("admit_watcher") is tick.default_admit_watcher
