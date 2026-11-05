"""Tests for jr/tick.py's overlap lock (incident 2026-10-09, #785): a real tick takes an exclusive
lock before any GitHub call, releases it after a tick or an abort, and a dry run takes none.

On the recorders of jr/test_tick.py: fake git, fake gh, a tmp checkout, no network.

Run: cd jr && python3 -m pytest test_tick_lock.py -v
"""
from __future__ import annotations

from pathlib import Path

import tick
from test_tick import NOW, REAL_REPO, checkout, gh_ok, git_ok, run, wt_dir  # noqa: F401 — checkout/wt_dir are fixtures


def test_a_held_lock_aborts_cleanly_before_any_github_call(tmp_path):
    import fcntl
    lock = tmp_path / "held.lock"
    gh = gh_ok()
    with open(lock, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = run(git=git_ok(tmp_path), gh=gh, lock_path=lock)
    assert r.aborted == f"another tick is running (lock held: {lock})"
    assert gh.calls == []


def test_the_lock_is_released_after_a_tick_and_after_an_abort(wt_dir, tmp_path):
    import fcntl
    lock = tmp_path / "run.lock"
    for gh in (gh_ok(), gh_ok(rate="1")):          # a clean tick, then an aborted one
        run(git=git_ok(wt_dir), gh=gh, lock_path=lock)
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)    # raises BlockingIOError if still held


def test_the_default_lock_lives_outside_the_repo_and_apart_from_the_wrapper_lock():
    # scripts/jr-tick.sh's `flock` holds /tmp/jr-tick.lock for its child's whole life; the tick
    # re-locking that same file would see it held by its own parent and abort every hour.
    # (conftest pins tick.DEFAULT_TICK_LOCK into tmp_path, so check what it is built from.)
    default = Path(tick.tempfile.gettempdir()) / tick.TICK_LOCK_NAME
    assert REAL_REPO not in default.parents
    assert tick.TICK_LOCK_NAME != "jr-tick.lock"


def test_main_honors_jr_tick_lock_from_the_environment(monkeypatch):
    seen = {}
    monkeypatch.setattr(tick, "run_tick", lambda **kw: seen.update(kw) or tick.report.TickReport(when=NOW))
    monkeypatch.setenv("JR_TICK_LOCK", "/run/jr/tick.lock")
    tick.main(["--no-telegram"])
    assert seen["lock_path"] == Path("/run/jr/tick.lock")
    monkeypatch.delenv("JR_TICK_LOCK")
    tick.main(["--no-telegram"])
    assert seen["lock_path"] is None


def test_dry_run_takes_no_lock(tmp_path):
    lock = tmp_path / "never.lock"
    run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), lock_path=lock)
    assert not lock.exists()


def test_an_unopenable_lock_aborts_closed(tmp_path):
    gh = gh_ok()
    r = run(git=git_ok(tmp_path), gh=gh, lock_path=tmp_path / "no-such-dir" / "x.lock")
    assert r.aborted.startswith("cannot open tick lock") and gh.calls == []
