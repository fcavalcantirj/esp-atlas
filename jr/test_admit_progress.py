"""The admit stall alarm (jr/admit_progress.py, SPEC-espatlas-jr.md): a launcher backlog that stops
shrinking is said out loud, once per UTC day, instead of being found by a human days later
(2026-11-12 to 2026-11-14: "admitted 0 · stopped before brucedevices/firmware" every hour, silent)."""
from __future__ import annotations

import json

import admit_progress as ap

WHERE = "stopped before brucedevices/firmware"


def tick(store, n, at, dry_run=False):
    return ap.watch(store, n, WHERE, at, dry_run=dry_run)


def test_three_flat_ticks_nudge_once_then_once_per_utc_day(tmp_path):
    s = ap.Store(tmp_path / "p.json")
    assert tick(s, 100, "2026-11-14T10:00:00+00:00")["nudges"] == []        # the baseline
    assert tick(s, 100, "2026-11-14T11:00:00+00:00")["nudges"] == []
    assert tick(s, 100, "2026-11-14T12:00:00+00:00")["nudges"] == []
    third = tick(s, 100, "2026-11-14T13:00:00+00:00")["nudges"]
    assert len(third) == 1 and "backlog 100" in third[0] and "3 ticks" in third[0] and WHERE in third[0]
    assert tick(s, 100, "2026-11-14T14:00:00+00:00")["nudges"] == []        # same UTC day: once
    assert len(tick(s, 100, "2026-11-15T00:00:00+00:00")["nudges"]) == 1     # the next UTC day: once more


def test_a_shrinking_tick_resets_the_count(tmp_path):
    s = ap.Store(tmp_path / "p.json")
    for h, n in ((10, 100), (11, 100), (12, 100), (13, 90), (14, 90), (15, 90)):
        assert tick(s, n, f"2026-11-14T{h}:00:00+00:00")["nudges"] == []
    assert len(tick(s, 90, "2026-11-14T16:00:00+00:00")["nudges"]) == 1


def test_a_growing_backlog_is_not_progress(tmp_path):
    s = ap.Store(tmp_path / "p.json")
    for h, n in ((10, 100), (11, 101), (12, 102)):
        tick(s, n, f"2026-11-14T{h}:00:00+00:00")
    assert len(tick(s, 103, "2026-11-14T13:00:00+00:00")["nudges"]) == 1


def test_an_empty_backlog_never_nudges_and_resets(tmp_path):
    s = ap.Store(tmp_path / "p.json")
    for h in range(10, 16):
        assert tick(s, 0, f"2026-11-14T{h}:00:00+00:00")["nudges"] == []
    assert json.loads((tmp_path / "p.json").read_text())["flat"] == 0


def test_a_dry_run_writes_and_sends_nothing(tmp_path):
    s = ap.Store(tmp_path / "p.json")
    for h in range(10, 16):
        assert tick(s, 100, f"2026-11-14T{h}:00:00+00:00", dry_run=True)["nudges"] == []
    assert not (tmp_path / "p.json").exists()


def test_a_corrupt_state_nudges_and_starts_over(tmp_path):
    (tmp_path / "p.json").write_text("{not json")
    s = ap.Store(tmp_path / "p.json")
    out = tick(s, 100, "2026-11-14T10:00:00+00:00")
    assert len(out["nudges"]) == 1 and "unreadable" in out["nudges"][0]
    assert json.loads((tmp_path / "p.json").read_text())["backlog"] == 100


def test_the_watch_never_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    out = ap.watch(ap.Store(blocker / "p.json"), 5, WHERE, "2026-11-14T10:00:00+00:00")   # parent is a file
    assert out["status"] == "unavailable" and out["nudges"] == []
