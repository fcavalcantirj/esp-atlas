"""One daily work slot PER SOURCE CLASS (SPEC-demand-work-consumer.md, Selection, budget and identity;
decision 2026-11-08): search demand and PAM market leads no longer share one slot, so a day with new
search demand still starts one PAM lead. `source_class` narrows a broker pass to one class: the
existing-work recovery, the new start and the daily cap are counted inside that class; the global
fail-closed checks (unreadable receipts, orphans, inconsistent closures) still block every pass.

Without a class filter the single shared budget of before is unchanged (test_pam_work_intake.py).
All sources are offline toy feeds/APIs; nothing reaches the network."""
import json

import pytest

import demand_broker as broker
import pam_leads as pam
import research_work as rw
from test_demand_broker import REAL_SNAPSHOT
from test_pam_work_intake import DAY, NEXT, ledger, prepare, reserve


def search_started(tmp_path):
    """fnk0104s (the snapshot's GSC UNRESOLVED item) reserved today in the search class."""
    prepare(tmp_path, catalog=[])
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_SEARCH)
    assert out.action == rw.START and ledger(tmp_path)["receipts"][0]["source"] == "gsc_query"
    return out


def settle(tmp_path, index, state="delivered"):
    doc = ledger(tmp_path)
    doc["receipts"][index]["state"] = state
    (tmp_path / broker.RECEIPTS_NAME).write_text(json.dumps(doc))


def test_the_classes_are_search_and_pam():
    assert rw.CLASS_SEARCH == "search" and rw.CLASS_PAM == "pam"
    assert rw.source_class(rw.SOURCE_PAM) == rw.CLASS_PAM
    assert rw.source_class("gsc_query") == rw.CLASS_SEARCH
    assert rw.source_class("ga4 search_empty") == rw.CLASS_SEARCH


def test_a_pam_lead_starts_the_same_day_a_search_item_started(tmp_path):
    search_started(tmp_path)
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.START and out.phase == rw.PHASE_RESEARCH
    rows = ledger(tmp_path)["receipts"]
    assert [r["source"] for r in rows] == ["gsc_query", "pam_feed"]
    assert rows[1]["started_on"] == DAY and rw._readable_receipt(rows[1])


def test_a_pam_pass_never_touches_search_work(tmp_path):
    search_started(tmp_path)
    before = ledger(tmp_path)["receipts"][0]
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.START and out.key.startswith("pam-")
    assert ledger(tmp_path)["receipts"][0] == before


def test_the_pam_class_has_its_own_daily_cap(tmp_path):
    search_started(tmp_path)
    reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    settle(tmp_path, 1)                       # today's PAM item is done; another eligible lead remains
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.DEFER and "daily cap" in out.reason and "pam" in out.reason
    assert len(ledger(tmp_path)["receipts"]) == 2


def test_the_search_class_has_its_own_daily_cap(tmp_path):
    search_started(tmp_path)
    settle(tmp_path, 0)
    snap = json.loads(json.dumps(REAL_SNAPSHOT))
    item = dict(next(i for i in snap["items"] if i["term"] == "fnk0104s"))
    item.update(term="es3n28p", raw_terms=["es3n28p"])
    snap["items"].append(item)                # a second UNRESOLVED search term the same day
    out = reserve(tmp_path, snap, source_class=rw.CLASS_SEARCH)
    assert out.action == rw.DEFER and "daily cap" in out.reason and "search" in out.reason


def test_a_search_item_starts_the_same_day_a_pam_lead_started(tmp_path):
    prepare(tmp_path, catalog=[])
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.START and out.key.startswith("pam-")
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_SEARCH)
    assert out.action == rw.START and ledger(tmp_path)["receipts"][1]["source"] == "gsc_query"


def test_live_pam_work_is_reconciled_inside_its_class_not_before_search(tmp_path):
    prepare(tmp_path, catalog=[])
    reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM, today=NEXT)
    assert out.action == rw.RESUME and out.key.startswith("pam-")        # one outstanding item per class
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_SEARCH, today=NEXT)
    assert out.action == rw.START and out.key and not out.key.startswith("pam-")


def test_live_search_work_is_reconciled_inside_its_class_not_before_pam(tmp_path):
    search_started(tmp_path)
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_SEARCH, today=NEXT)
    assert out.action == rw.RESUME and out.key == ledger(tmp_path)["receipts"][0]["key"]
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM, today=NEXT)
    assert out.action == rw.START and out.key.startswith("pam-")


def test_global_fail_closed_checks_block_every_class(tmp_path):
    search_started(tmp_path)
    doc = ledger(tmp_path)
    doc["receipts"][0]["state"] = "half-done"           # corrupt receipt
    (tmp_path / broker.RECEIPTS_NAME).write_text(json.dumps(doc))
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.DEFER and "corrupt" in out.reason
    assert len(ledger(tmp_path)["receipts"]) == 1


def test_an_orphan_search_receipt_blocks_the_pam_class_too(tmp_path):
    search_started(tmp_path)
    snap = {**REAL_SNAPSHOT, "items": [i for i in REAL_SNAPSHOT["items"] if i["gap"] != "UNRESOLVED"]}
    out = reserve(tmp_path, snap, source_class=rw.CLASS_PAM)
    assert out.action == rw.DEFER and "matches no open candidate" in out.reason


def test_an_unknown_class_is_refused_before_anything_is_read(tmp_path):
    prepare(tmp_path, catalog=[])
    with pytest.raises(ValueError):
        reserve(tmp_path, REAL_SNAPSHOT, source_class="market")
    assert not (tmp_path / broker.RECEIPTS_NAME).exists()


def test_plan_work_without_a_class_keeps_the_single_shared_budget():
    """Direct callers that pass no class see the old rule: one new item per day across both classes."""
    import inspect
    assert inspect.signature(rw.plan_work).parameters["source_class"].default is None
