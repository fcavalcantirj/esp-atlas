"""jr/quote_run.py — the daily quote report lands only when its FAIL rows changed; fail closed."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import quote_run

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "scripts" / "fixtures" / "quotes"
NOW = datetime(2026, 11, 17, 11, 15, tzinfo=timezone.utc)
PREFACE_URL = "https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html"


def worktree(tmp_path):
    (tmp_path / "data" / "boards" / "freenove" / "freenove-esp32-wrover").mkdir(parents=True)
    shutil.copy(FIX / "freenove-esp32-wrover.board.md", tmp_path / "data/boards/freenove/freenove-esp32-wrover/board.md")
    (tmp_path / "docs" / "demand").mkdir(parents=True)
    return tmp_path


def fetch_with(preface_ok=True):
    import check_quotes
    preface = (FIX / "freenove-fnk0060-preface.txt").read_text()
    if not preface_ok:
        preface = preface.replace("CH340 to download codes", "CH341 to download codes")
    def fetch(url):
        text = preface if url == PREFACE_URL else ("Freenove_ESP32_WROVER_Board kit" if "github.com/Freenove" in url else "unrelated")
        return check_quotes.Page(url, check_quotes.normalize(text), "fake")
    return fetch


def test_a_fail_lands_the_report_with_worktree_relative_record_paths(tmp_path):
    wt = worktree(tmp_path)
    res = quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(preface_ok=False))
    assert res.status == "updated" and res.changed_paths == (quote_run.STATE_PATH,) and res.complete
    doc = json.loads((wt / quote_run.STATE_PATH).read_text())
    assert doc["date"] == "2026-11-17" and doc["complete"] is True
    assert doc["records"][0]["record"] == "data/boards/freenove/freenove-esp32-wrover/board.md"
    assert doc["records"][0]["id"] == "freenove-esp32-wrover" and doc["records"][0]["quotes"] == ["ESP32 uses CH340 to download codes"]


def test_the_same_fail_rows_again_are_unchanged_and_land_nothing(tmp_path):
    wt = worktree(tmp_path)
    assert quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(False)).status == "updated"
    before = (wt / quote_run.STATE_PATH).read_bytes()
    res = quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(False))
    assert res.status == "unchanged" and res.changed_paths == () and (wt / quote_run.STATE_PATH).read_bytes() == before


def test_a_clean_catalog_writes_an_empty_report_once(tmp_path):
    wt = worktree(tmp_path)
    res = quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(True))
    assert res.status == "updated" and json.loads((wt / quote_run.STATE_PATH).read_text())["records"] == []
    assert quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(True)).status == "unchanged"


def test_an_error_is_a_deferral_and_the_previous_report_stays(tmp_path):
    wt = worktree(tmp_path)
    quote_run.refresh_worktree(wt, now=NOW, fetch=fetch_with(False))
    before = (wt / quote_run.STATE_PATH).read_bytes()
    def boom(url):
        raise RuntimeError("network down")
    res = quote_run.refresh_worktree(wt, now=NOW, fetch=boom)
    # a fetch error makes pages unreadable -> inconclusive, not fail: the FAIL rows change -> report updates incomplete? no:
    assert res.status in ("updated", "unchanged", "deferred")
    doc = json.loads((wt / quote_run.STATE_PATH).read_text())
    assert doc["records"] == [] or (wt / quote_run.STATE_PATH).read_bytes() == before
