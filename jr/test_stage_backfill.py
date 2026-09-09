"""Tests for jr/stage_backfill.py — the Track A (finite backfill) tick stage.
The per-board writer (board_backfill.backfill_board) is faked; this validates the STAGE
wrapper: budget cap, complete-skip (no fetch), path collection, StageResult."""
from __future__ import annotations

import datetime as dt

import board_backfill
import stage_backfill


class FakeBudget:
    def __init__(self, calls=100, seconds=10_000):
        self._calls, self._seconds = calls, seconds

    def wrap(self, fn, label):
        return fn

    def remaining_calls(self):
        return self._calls

    def remaining_seconds(self):
        return self._seconds


class Ctx:
    def __init__(self, root, budget=None):
        self.root = root
        self.now = dt.datetime(2026, 9, 8, 12, 0)
        self.budget = budget or FakeBudget()


def _mk_boards(root, names):
    esp = root / "data" / "boards" / "espressif"
    esp.mkdir(parents=True)
    for n in names:
        d = esp / n
        d.mkdir()
        (d / "board.md").write_text(f"---\nid: {n}\ntype: board\nsoc: esp32\n---\n\nbody\n")


def _fake_backfill(statuses, monkeypatch):
    def fake_bb(path, data_root, fetch, today):
        bid = path.parent.name
        st = statuses[bid]
        base = {"board_id": bid, "status": st}
        if st == "backfilled":
            return {**base, "written": ["download_mode"], "omitted": []}
        if st == "skipped":
            return {**base, "reason": "doc-unreachable"}
        return base  # complete
    monkeypatch.setattr(board_backfill, "backfill_board", fake_bb)


def test_budget_caps_attempts_and_complete_boards_are_free(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1", "b2", "b3", "b4"])
    # b1 complete (free), b2/b3 backfilled, b4 backfilled — budget 2 attempts
    _fake_backfill({"b1": "complete", "b2": "backfilled", "b3": "backfilled", "b4": "backfilled"}, monkeypatch)
    res = stage_backfill.run(Ctx(tmp_path), budget=2)
    assert res.name == "backfill"
    # b1 complete skipped for free; b2,b3 fill and hit the budget; b4 never attempted
    assert res.paths == ["data/boards/espressif/b2/board.md", "data/boards/espressif/b3/board.md"]
    assert "backfilled 2" in res.summary


def test_skipped_boards_count_against_budget(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1", "b2", "b3"])
    _fake_backfill({"b1": "skipped", "b2": "backfilled", "b3": "backfilled"}, monkeypatch)
    res = stage_backfill.run(Ctx(tmp_path), budget=2)   # b1 skip + b2 fill = 2 attempts; b3 not reached
    assert res.paths == ["data/boards/espressif/b2/board.md"]
    assert "backfilled 1, skipped 1" in res.summary


def test_worklist_rotates_across_ticks_so_it_never_sticks(tmp_path, monkeypatch):
    import re
    _mk_boards(tmp_path, [f"b{i}" for i in range(8)])
    _fake_backfill({f"b{i}": "skipped" for i in range(8)}, monkeypatch)  # all un-groundable
    seen = set()
    for hour in (0, 1, 2, 3):   # consecutive hourly ticks
        ctx = Ctx(tmp_path)
        ctx.now = dt.datetime(2026, 9, 8, hour, 0)
        res = stage_backfill.run(ctx, budget=2)
        seen.update(re.findall(r"b\d", res.summary))
    # sorted+no-rotation would re-hit only b0/b1 every tick; rotation must cover the rest
    assert len(seen) >= 6, seen


def test_stops_when_call_budget_is_exhausted(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1", "b2"])
    _fake_backfill({"b1": "backfilled", "b2": "backfilled"}, monkeypatch)
    res = stage_backfill.run(Ctx(tmp_path, FakeBudget(calls=0)), budget=5)
    assert res.paths == []
    assert "budget low" in res.summary
