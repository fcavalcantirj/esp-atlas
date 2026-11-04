"""Tests for jr/board_cooldown.py and its use in jr/stage_backfill.py — G3a (c): a board on which
every source failed is cooled down for 7 days, so the hourly budget moves to boards that can
still be filled; the stage summary carries each skip's per-field reasons."""
from __future__ import annotations

import datetime as dt
import json

import board_backfill
import board_cooldown
import stage_backfill
import tick
from test_stage_backfill import Ctx, _mk_boards

T0 = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
REASONS = {"usb_serial": {"vendor": "field_absent", "manifest": "no_manifest"},
           "download_mode": {"vendor": "no_pattern_match", "manifest": "field_absent"}}


def _fake(statuses, calls, monkeypatch):
    def fake_bb(path, data_root, fetch, today):
        bid = path.parent.name
        calls.append(bid)
        st = statuses[bid]
        if st == "backfilled":
            return {"board_id": bid, "status": st, "written": ["usb_serial"], "omitted": []}
        return {"board_id": bid, "status": "skipped", "reason": "nothing-groundable",
                "field_reasons": REASONS}
    monkeypatch.setattr(board_backfill, "backfill_board", fake_bb)


def _tick(root, now, budget=4):
    ctx = Ctx(root)
    ctx.now = now
    return stage_backfill.run(ctx, budget=budget)


# ── the store ─────────────────────────────────────────────────────────────────

def test_record_then_cooling_until_seven_days_pass(tmp_path):
    path = tmp_path / "jr" / "board_cooldown.json"
    store = board_cooldown.load(path)
    board_cooldown.record(store, "b1", "nothing-groundable", REASONS, now=T0)
    board_cooldown.save(store, path, now=T0)
    store = board_cooldown.load(path)
    assert board_cooldown.is_cooling(store, "b1", now=T0 + dt.timedelta(days=6, hours=23))
    assert not board_cooldown.is_cooling(store, "b1", now=T0 + dt.timedelta(days=7))
    assert not board_cooldown.is_cooling(store, "b2", now=T0)
    rec = json.loads(path.read_text())["by_board"]["b1"]
    assert rec["reason"] == "nothing-groundable"
    assert rec["field_reasons"] == REASONS
    assert rec["expires"] == (T0 + dt.timedelta(days=board_cooldown.COOLDOWN_DAYS)).isoformat()


def test_save_prunes_expired_records(tmp_path):
    path = tmp_path / "board_cooldown.json"
    store = board_cooldown.load(path)
    board_cooldown.record(store, "old", "doc-unreachable", {}, now=T0)
    board_cooldown.record(store, "new", "doc-unreachable", {}, now=T0 + dt.timedelta(days=5))
    board_cooldown.save(store, path, now=T0 + dt.timedelta(days=8))
    assert set(json.loads(path.read_text())["by_board"]) == {"new"}


def test_missing_or_corrupt_file_loads_empty(tmp_path):
    assert board_cooldown.load(tmp_path / "nope.json") == {"by_board": {}}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert board_cooldown.load(bad) == {"by_board": {}}


# ── the stage ─────────────────────────────────────────────────────────────────

def test_fully_failed_board_is_not_retried_for_7_days_then_comes_back(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1"])
    calls: list = []
    _fake({"b1": "skipped"}, calls, monkeypatch)

    first = _tick(tmp_path, T0)
    assert calls == ["b1"]
    assert board_cooldown.RELPATH in first.paths          # the decision ships with the tick

    for hours in (1, 24, 6 * 24 + 23):
        res = _tick(tmp_path, T0 + dt.timedelta(hours=hours))
        assert calls == ["b1"], f"retried after {hours}h"
        assert "cooling 1" in res.summary

    _tick(tmp_path, T0 + dt.timedelta(days=7))
    assert calls == ["b1", "b1"]


def test_cooled_boards_cost_no_budget_so_fillable_boards_get_it(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b0", "b1", "b2", "b3"])
    calls: list = []
    _fake({"b0": "skipped", "b1": "skipped", "b2": "backfilled", "b3": "backfilled"}, calls, monkeypatch)
    store = board_cooldown.load(tmp_path / board_cooldown.RELPATH)
    for b in ("b0", "b1"):
        board_cooldown.record(store, b, "nothing-groundable", REASONS, now=T0)
    board_cooldown.save(store, tmp_path / board_cooldown.RELPATH, now=T0)

    res = _tick(tmp_path, T0 + dt.timedelta(hours=1), budget=2)
    assert sorted(calls) == ["b2", "b3"]
    assert "backfilled 2" in res.summary


def test_backfilled_board_is_never_cooled(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1"])
    _fake({"b1": "backfilled"}, [], monkeypatch)
    res = _tick(tmp_path, T0)
    assert board_cooldown.RELPATH not in res.paths
    assert not (tmp_path / board_cooldown.RELPATH).exists()


def test_skip_line_carries_per_field_reasons(tmp_path, monkeypatch):
    _mk_boards(tmp_path, ["b1"])
    _fake({"b1": "skipped"}, [], monkeypatch)
    res = _tick(tmp_path, T0)
    assert "b1: skip nothing-groundable" in res.summary
    assert "usb_serial=field_absent/no_manifest" in res.summary
    assert "download_mode=no_pattern_match/field_absent" in res.summary
    assert "cooled 1 for 7d" in res.summary


def test_cooldown_file_is_tick_bookkeeping():
    assert board_cooldown.RELPATH == "jr/board_cooldown.json"
    assert tick._is_bookkeeping(board_cooldown.RELPATH)
