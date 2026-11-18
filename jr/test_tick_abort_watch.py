"""SPEC-jr-self-heal.md §1c at the tick: every hourly tick hands its outcome to the abort watcher — the abort
reason, or None when it completed — after its worktree and lock are released; a broken watcher never
changes the tick's outcome. Fake git/gh only (test_tick's helpers)."""
from __future__ import annotations

import tick
from test_tick import git_ok, gh_ok, run, wt_dir  # noqa: F401 — wt_dir is a fixture


def _watcher(calls, answer=None, boom=False):
    def w(reason, now, dry_run):
        calls.append((reason, dry_run))
        if boom:
            raise RuntimeError("store on fire")
        return answer if answer is not None else {"status": "ok", "incidents": [], "resolved": [], "nudges": []}
    return w


def test_an_aborted_tick_hands_its_reason_to_the_watcher(tmp_path):
    calls = []
    r = run(git=git_ok(tmp_path), gh=gh_ok(rate="120"), abort_watcher=_watcher(
        calls, {"status": "ok", "incidents": ["abc123def456"], "resolved": [], "nudges": [], "consecutive": 2}))
    assert r.aborted == "GitHub rate limit low: 120 < 500"
    assert calls == [("GitHub rate limit low: 120 < 500", False)]
    assert r.abort_watch["incidents"] == ["abc123def456"]
    assert any("abort incident abc123def456" in w for w in r.warnings)


def test_a_completed_tick_hands_none_to_the_watcher(wt_dir):
    calls = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(), abort_watcher=_watcher(calls))
    assert not r.aborted and calls == [(None, False)]


def test_a_broken_watcher_never_changes_the_outcome(tmp_path):
    calls = []
    r = run(git=git_ok(tmp_path), gh=gh_ok(rate="120"), abort_watcher=_watcher(calls, boom=True))
    assert r.aborted == "GitHub rate limit low: 120 < 500" and calls
    assert r.abort_watch["status"] == "unavailable"
    assert any("abort watch unavailable" in w for w in r.warnings)


def test_the_hourly_main_wires_the_default_watcher():
    import inspect
    assert "abort_watcher=default_abort_watcher" in inspect.getsource(tick.main)
