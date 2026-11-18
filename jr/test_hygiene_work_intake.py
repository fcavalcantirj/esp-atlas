"""The daily quote report -> a hygiene reservation (class `hygiene`, SPEC-demand-work-consumer.md
"Hygiene: quote FAILs become work"). Offline: the report is a fixture, gh is a recorder."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

import demand_broker as broker
import research_work as rw
import work_record
from test_demand_broker import REAL_SNAPSHOT, SLUG, gh_remote, without_unresolved

DAY = "2026-11-17"
SNAP = without_unresolved(REAL_SNAPSHOT)
ROW = {"record": "data/boards/m5stack/m5dial/board.md", "id": "m5dial",
       "quotes": ["PORT.A | G13 | G15", "PORT.B | G2 | G1"], "urls": ["https://docs.m5stack.com/en/core/M5Dial"]}
ROW2 = {"record": "data/boards/seeed/xiao-esp32c5/board.md", "id": "xiao-esp32c5",
        "quotes": ["you can draw NmA"], "urls": ["https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/"]}


def report(*rows, date=DAY, complete=True):
    return {"version": 1, "date": date, "complete": complete, "records": [deepcopy(r) for r in rows],
            "counts": {"records": len(rows)}}


def prepare(path, *rows, **kw):
    path.mkdir(exist_ok=True)
    (path / "research-queue.json").write_text(json.dumps({"version": 1, "candidates": {}}))
    (path / broker.QUOTE_REPORT_NAME).write_text(json.dumps(report(*rows, **kw)))


def reserve(path, **kw):
    return broker.reserve(path, SNAP, gh=kw.pop("gh", gh_remote()), today=kw.pop("today", DAY), repo_slug=SLUG,
                          new_pam=False, source_class=rw.CLASS_HYGIENE, **kw)


def ledger(path):
    return json.loads((path / broker.RECEIPTS_NAME).read_text())


def test_a_fail_record_in_the_report_becomes_one_hygiene_reservation_with_its_row_as_provenance(tmp_path):
    prepare(tmp_path, ROW)
    out = reserve(tmp_path, new_quote=True)
    assert out.action == rw.START and out.phase == rw.PHASE_RESEARCH and out.key == rw.quote_key({**ROW, "report_date": DAY})
    row = ledger(tmp_path)["receipts"][0]
    assert row["source"] == rw.SOURCE_QUOTE and row["term"] == "quote fix m5dial"
    assert row["quote"] == {**ROW, "report_date": DAY} and row["candidate"]["quote"] == row["quote"]
    assert "window" not in row and "metrics" not in row and rw._readable_receipt(row)
    assert row["branch"] == rw.branch_for(out.key)


def test_without_the_new_quote_flag_or_an_incomplete_report_no_hygiene_work_starts(tmp_path):
    prepare(tmp_path, ROW)
    assert reserve(tmp_path, new_quote=False).action == rw.NOOP
    prepare(tmp_path, ROW, complete=False)
    assert reserve(tmp_path, new_quote=True).action == rw.NOOP


def test_one_hygiene_item_a_day_and_a_record_already_open_is_not_reserved_twice(tmp_path):
    prepare(tmp_path, ROW, ROW2)
    first = reserve(tmp_path, new_quote=True)
    assert first.action == rw.START
    second = reserve(tmp_path, new_quote=True)
    assert second.action in (rw.DEFER, rw.RECONCILE) and "daily cap" in second.reason or second.action == rw.RECONCILE
    # the next day: the open record is recovered, not duplicated; the other record may start
    nxt = reserve(tmp_path, new_quote=True, today="2026-11-18")
    assert nxt.action in (rw.RESUME, rw.RECONCILE)
    keys = {r["key"] for r in ledger(tmp_path)["receipts"]}
    assert len(keys) == 1


def test_a_later_report_without_the_record_keeps_the_open_reservation(tmp_path):
    prepare(tmp_path, ROW)
    reserve(tmp_path, new_quote=True)
    prepare(tmp_path, ROW2, date="2026-11-18")                    # the record no longer fails; receipts kept
    nxt = reserve(tmp_path, new_quote=True, today="2026-11-18")
    assert nxt.action in (rw.RESUME, rw.RECONCILE)                 # the open work recovers first
    assert len(ledger(tmp_path)["receipts"]) == 1


def test_an_unreadable_report_starts_nothing_and_says_so(tmp_path):
    prepare(tmp_path, ROW)
    (tmp_path / broker.QUOTE_REPORT_NAME).write_text("{not json")
    out = reserve(tmp_path, new_quote=True)
    assert out.action in (rw.NOOP, rw.DEFER) and "quote report" in out.reason


def test_adopt_materializes_the_hygiene_candidate_in_the_queue(tmp_path):
    prepare(tmp_path, ROW)
    out = reserve(tmp_path, new_quote=True)
    cand = work_record.adopt(tmp_path, out.key, today=DAY)
    q = json.loads((tmp_path / "research-queue.json").read_text())
    assert out.key in q["candidates"] and q["candidates"][out.key]["source"] == rw.SOURCE_QUOTE
    assert cand["quote"]["record"] == ROW["record"]
    v = work_record.validate(tmp_path, out.key, {"validated_by": "executor test", "primary_sources": ROW["urls"],
                                                 "expected_ids": ["m5dial"]}, today=DAY)
    assert v["validation"]["verification_kind"] == rw.KIND_CATALOG_QUOTE
