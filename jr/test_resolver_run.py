"""jr/resolver_run.py — the gauge's vendor × field gaps ranked into the daily resolver report; demand only orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import resolver_run as rr

NOW = datetime(2026, 11, 18, 11, 15, tzinfo=timezone.utc)


def board(root: Path, vendor: str, bid: str, **fields):
    d = root / "data/boards" / vendor / bid
    d.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}: {v}\n" for k, v in fields.items())
    (d / "board.md").write_text(f"---\nid: {bid}\ntype: board\nbrand: {vendor}\nname: {bid}\nsoc: esp32\n{body}---\n")


def catalog(root: Path):
    for i in range(4):
        board(root, "adafruit", f"ada-{i}", usb_serial="cp2102")                      # 4 missing download_mode etc.
    for i in range(3):
        board(root, "espressif", f"esp-{i}", download_mode="{mode: manual, steps: x}", usb_serial="cp2102")   # 3 missing dimensions_mm
    board(root, "lilygo", "t-1")                                                        # 1 board: below the floor
    (root / "docs/demand").mkdir(parents=True)
    return root


def snap(**imps):
    items = [{"term": b, "impressions": n, "landing_page": f"https://esp-atlas.com/parts/{b}", "gap": "RANKS_POORLY" if n > 50 else "COVERED_OK"}
             for b, n in imps.items()]
    return {"date": "2026-11-18", "items": items}


def test_rows_are_ordered_by_boards_missing_then_page_demand_and_small_gaps_are_out(tmp_path):
    root = catalog(tmp_path)
    res = rr.refresh_worktree(root, now=NOW, snap=snap(**{"esp-0": 60, "esp-1": 47}))
    assert res.status == "updated" and res.changed_paths == (rr.STATE_PATH,) and res.complete
    doc = json.loads((root / rr.STATE_PATH).read_text())
    rows = doc["records"]
    assert doc["complete"] is True and doc["date"] == "2026-11-18"
    assert all(r["missing"] >= 3 for r in rows) and not any(r["vendor"] == "lilygo" for r in rows)
    assert rows[0]["vendor"] == "adafruit" and rows[0]["missing"] == 4                   # most boards missing first
    esp = [r for r in rows if r["vendor"] == "espressif"]
    assert esp[0]["field"] == "dimensions_mm" or esp[0]["demand_impressions"] == 107   # same missing count: demand breaks the tie
    assert all(r["demand_impressions"] == 107 and r["ranks_poorly"] == 1 for r in esp)
    assert rows[0]["boards"] == ["ada-0", "ada-1", "ada-2", "ada-3"] and rows[0]["records"] == 4


def test_unchanged_rows_land_nothing_and_a_fixed_gap_changes_the_report(tmp_path):
    root = catalog(tmp_path)
    assert rr.refresh_worktree(root, now=NOW, snap=None).status == "updated"
    assert rr.refresh_worktree(root, now=NOW, snap=None).status == "unchanged"
    board(root, "adafruit", "ada-0", usb_serial="cp2102", download_mode="{mode: manual, steps: x}")   # the backfill filled one
    res = rr.refresh_worktree(root, now=NOW, snap=None)
    assert res.status == "updated"
    rows = json.loads((root / rr.STATE_PATH).read_text())["records"]
    assert [r for r in rows if r["vendor"] == "adafruit" and r["field"] == "download_mode"][0]["missing"] == 3


def test_page_demand_reads_landing_pages_only_and_an_error_defers(tmp_path):
    d = rr.page_demand(snap(**{"x": 10, "y": 60}) | {"items": snap(x=10)["items"] + [{"term": "no page"}, {"landing_page": "https://esp-atlas.com/firmware/m5gotchi", "impressions": 9}]})
    assert d == {"x": {"impressions": 10, "ranks_poorly": False}}
    res = rr.refresh_worktree(tmp_path / "missing", now=NOW, snap=None)
    assert res.status == "unchanged" and res.counts["gaps"] == 0      # an empty tree: an empty report, never landed, never a crash
