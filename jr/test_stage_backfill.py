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
    _mk_brand_boards(root, "espressif", names)


def _mk_brand_boards(root, brand, names):
    d = root / "data" / "boards" / brand
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        bd = d / n
        bd.mkdir()
        (bd / "board.md").write_text(
            f"---\nid: {n}\ntype: board\nbrand: {brand}\nsoc: esp32-s3\n---\n\nbody\n")


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


def test_run_reaches_m5stack_boards_and_backfills_getting_started(tmp_path):
    # REAL board_backfill (not faked) + an injected 200 fetch: proves the stage's worklist
    # now includes a REGISTERED non-Espressif vendor (m5stack). m5cardputer is a real board
    # id in board_backfill.M5STACK_DOC_PATHS, so its resolver yields a candidate URL and the
    # 200 fetch grounds getting_started. RED against the old espressif-only glob (which never
    # reaches m5stack -> res.paths == []).
    _mk_brand_boards(tmp_path, "m5stack", ["m5cardputer"])

    def fetch(url):
        return {"ok": True, "status": 200,
                "text": "<html><body><p>Getting started with M5Cardputer.</p></body></html>"}

    res = stage_backfill.run(Ctx(tmp_path), budget=4, fetch=fetch)
    assert res.paths == ["data/boards/m5stack/m5cardputer/board.md"]
    assert "m5cardputer" in res.summary
    # getting_started is always groundable once the doc resolves 200
    body = (tmp_path / "data/boards/m5stack/m5cardputer/board.md").read_text()
    assert "getting_started" in body


def test_brand_without_a_registered_resolver_is_not_in_the_worklist(tmp_path, monkeypatch):
    # A brand with NO resolver in VENDOR_DOC_RESOLVERS -> its boards must never be fed to the
    # per-board backfill, while espressif (registered) still is. (All 13 real brands now have
    # resolvers as of Slice 13, so a fictional unregistered brand pins the "no-resolver → never
    # fed" rule.)
    _mk_brand_boards(tmp_path, "espressif", ["esp32-c3-devkitc-2"])
    _mk_brand_boards(tmp_path, "noresolver-vendor", ["noresolver-vendor-esp32-s3-touch"])
    seen = []

    def fake_bb(path, data_root, fetch, today):
        seen.append(str(path))
        return {"board_id": path.parent.name, "status": "skipped", "reason": "x"}

    monkeypatch.setattr(board_backfill, "backfill_board", fake_bb)
    stage_backfill.run(Ctx(tmp_path), budget=10)
    assert any(p.endswith("espressif/esp32-c3-devkitc-2/board.md") for p in seen)
    assert not any("noresolver-vendor" in p for p in seen)
