"""The daily resolver report -> a resolver reservation (class `resolver`, SPEC-demand-work-consumer.md
"Resolver work"). Offline: the report is a fixture, gh is a recorder."""
from __future__ import annotations

import json
from copy import deepcopy

import demand_broker as broker
import research_work as rw
import work_record
from test_demand_broker import REAL_SNAPSHOT, SLUG, gh_remote, without_unresolved

DAY = "2026-11-18"
SNAP = without_unresolved(REAL_SNAPSHOT)
ROW = {"vendor": "adafruit", "field": "download_mode", "missing": 20, "records": 26,
       "boards": ["adafruit-feather-esp32-s3", "adafruit-qtpy-esp32-c3", "adafruit-metro-esp32-s3"], "demand_impressions": 0}
ROW2 = {"vendor": "espressif", "field": "dimensions_mm", "missing": 17, "records": 19,
        "boards": ["esp32-s3-devkitc-1", "esp32-c6-devkitc-1", "esp32-p4-function-ev-board"], "demand_impressions": 107}


def report(*rows, date=DAY, complete=True):
    return {"version": 1, "date": date, "complete": complete, "records": [deepcopy(r) for r in rows],
            "counts": {"records": len(rows)}}


def prepare(path, *rows, **kw):
    path.mkdir(exist_ok=True)
    (path / "research-queue.json").write_text(json.dumps({"version": 1, "candidates": {}}))
    (path / broker.RESOLVER_REPORT_NAME).write_text(json.dumps(report(*rows, **kw)))


def reserve(path, **kw):
    return broker.reserve(path, SNAP, gh=kw.pop("gh", gh_remote()), today=kw.pop("today", DAY), repo_slug=SLUG,
                          new_pam=False, source_class=rw.CLASS_RESOLVER, **kw)


def ledger(path):
    return json.loads((path / broker.RECEIPTS_NAME).read_text())


def prov(row, date=DAY):
    return {**{k: row[k] for k in ("vendor", "field", "missing", "records", "boards")}, "report_date": date}


def test_the_top_gap_becomes_one_resolver_reservation_with_the_row_as_provenance(tmp_path):
    prepare(tmp_path, ROW, ROW2)
    out = reserve(tmp_path, new_resolver=True)
    assert out.action == rw.START and out.phase == rw.PHASE_RESEARCH and out.key == rw.resolver_key(prov(ROW))
    row = ledger(tmp_path)["receipts"][0]
    assert row["source"] == rw.SOURCE_RESOLVER and row["term"] == "resolver adafruit download_mode"
    assert row["resolver"] == prov(ROW) and row["candidate"]["resolver"] == row["resolver"]
    assert "window" not in row and "metrics" not in row and rw._readable_receipt(row)
    assert row["branch"] == rw.branch_for(out.key)


def test_without_the_flag_or_a_complete_report_no_resolver_work_starts(tmp_path):
    prepare(tmp_path, ROW)
    assert reserve(tmp_path, new_resolver=False).action == rw.NOOP
    prepare(tmp_path, ROW, complete=False)
    assert reserve(tmp_path, new_resolver=True).action == rw.NOOP
    (tmp_path / broker.RESOLVER_REPORT_NAME).unlink()
    out = reserve(tmp_path, new_resolver=True)
    assert out.action == rw.NOOP and "resolver report unreadable or absent" in out.reason


def test_one_item_a_day_and_an_open_gap_is_never_reserved_twice(tmp_path):
    prepare(tmp_path, ROW, ROW2)
    assert reserve(tmp_path, new_resolver=True).action == rw.START
    second = reserve(tmp_path, new_resolver=True)
    assert second.action != rw.START
    nxt = reserve(tmp_path, new_resolver=True, today="2026-11-19")
    assert nxt.action in (rw.RESUME, rw.RECONCILE)
    keys = {r["key"] for r in ledger(tmp_path)["receipts"]}
    assert keys == {rw.resolver_key(prov(ROW))}                                   # the same gap on a later report: same job


def test_a_row_the_broker_cannot_read_is_skipped_not_fatal(tmp_path):
    prepare(tmp_path, {**ROW, "field": "pinouts"}, ROW2)
    out = reserve(tmp_path, new_resolver=True)
    assert out.action == rw.START and out.key == rw.resolver_key(prov(ROW2))


def test_the_resolver_class_never_takes_the_search_pam_or_hygiene_slot(tmp_path):
    prepare(tmp_path, ROW)
    for cls in (rw.CLASS_SEARCH, rw.CLASS_PAM, rw.CLASS_HYGIENE):
        out = broker.reserve(tmp_path, SNAP, gh=gh_remote(), today=DAY, repo_slug=SLUG, new_pam=False,
                             source_class=cls, new_resolver=True)
        assert out.action != rw.START, cls


def test_adopt_rebuilds_the_candidate_from_the_receipt_snapshot(tmp_path):
    prepare(tmp_path, ROW)
    out = reserve(tmp_path, new_resolver=True)
    q = tmp_path / "research-queue.json"
    q.write_text(json.dumps({"version": 1, "candidates": {}}))              # the committed queue lost the row (a stale base)
    work_record.main(["--demand-dir", str(tmp_path), "adopt", out.key, "--date", DAY])
    cands = json.loads(q.read_text())["candidates"]
    assert len(cands) == 1 and next(iter(cands.values()))["resolver"] == prov(ROW)


def test_a_later_report_with_a_new_date_keeps_the_open_reservation(tmp_path):
    """Review BLOCK of #2137: the resolver report is rewritten almost daily (its rows change as the backfill
    fills fields), and its keys carry the report date. A live reservation must stay in the broker's view, or it
    becomes an orphan and plan_work DEFERs every class until someone repairs the queue by hand."""
    prepare(tmp_path, ROW)
    first = reserve(tmp_path, new_resolver=True)
    assert first.action == rw.START
    (tmp_path / broker.RESOLVER_REPORT_NAME).write_text(
        json.dumps(report(dict(ROW, missing=19), date="2026-11-19")))           # the same gap, a new day's report
    nxt = reserve(tmp_path, new_resolver=True, today="2026-11-19")
    assert nxt.action != rw.DEFER and nxt.action in (rw.RESUME, rw.RECONCILE, rw.NOOP), nxt
    assert len(ledger(tmp_path)["receipts"]) == 1                              # never a second job for the gap
