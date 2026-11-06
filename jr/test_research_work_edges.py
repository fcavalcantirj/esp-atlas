"""Fail-closed edges of jr/research_work.py beyond the contract oracles in test_research_work.py.
Controlled fixtures only, never production events."""
from copy import deepcopy

import pytest

import research_queue
import research_work as rw
from test_research_work import (DAY, candidate, linked, live_receipt, mined_receipt, queue,
                                reserve, validation)


@pytest.mark.parametrize("term", ["ESP32-C6", " esp32_c6! ", "Módulo X", "开发板", "", None])
def test_term_key_matches_the_research_queue_dedupe_key(term):
    assert rw.term_key(term) == research_queue.term_key(term)


@pytest.mark.parametrize("today,q", [("not-a-date", queue(candidate())), (DAY, {"candidates": []}),
                                     (DAY, None), (DAY, {"candidates": {"x": "row"}})])
def test_unreadable_run_date_or_queue_defers(today, q):
    assert rw.plan_work(q, [], today, remote_complete=True).action == "defer"


def test_remote_listing_is_assumed_incomplete_unless_stated():
    assert rw.plan_work(queue(candidate()), [], DAY).action == "defer"


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(status="triaged"),
    lambda c: c.update(window="2026-10-07..2026-11-04"),
    lambda c: c.update(window={"start": "2026-11-04", "end": "2026-10-07"}),
    lambda c: [c.pop("searches"), c.pop("zero_result_searches")],
    lambda c: c.update(first_seen=None),
    lambda c: c.update(source=""),
    lambda c: c.update(term="!!!"),
])
def test_unreadable_candidate_fails_closed(mutate):
    c = candidate()
    mutate(c)
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).action == "defer"


@pytest.mark.parametrize("fields", [{"last_attempt_on": "yesterday"}, {"branch": "jr/research-other"},
                                    {"state": "mystery"}, {"pr_url": ""}, {"started_on": None}])
def test_receipts_with_unreadable_fields_are_corrupt(fields):
    c = candidate()
    assert rw.plan_work(queue(c), [reserve(c, **fields)], DAY, remote_complete=True).action == "defer"


def test_outstanding_work_matching_no_open_candidate_blocks_new_work():
    orphan = reserve(candidate("gone123x"), started_on="2026-11-01", last_attempt_on="2026-11-01")
    p = rw.plan_work(queue(candidate()), [orphan], DAY, remote_complete=True)
    assert p.action == "defer" and "matches no open candidate" in p.reason


def test_settled_work_is_not_restarted_in_the_same_lifecycle():
    c = candidate()
    done = reserve(c, state="rejected", started_on="2026-11-01")
    assert rw.plan_work(queue(c), [done], DAY, remote_complete=True).action == "noop"


def test_authoring_ready_candidate_starts_before_research():
    ready = candidate("zzz123x", "validated")
    ready["validation"] = validation("zzz123x")
    p = rw.plan_work(queue(candidate("aaa123x"), ready), [], DAY, remote_complete=True)
    assert p.action == "start" and p.work.term == "zzz123x" and p.work.phase == "author"


@pytest.mark.parametrize("change", [
    lambda c, pr: c.update(status="closed"),
    lambda c, pr: c.pop("validation"),
    lambda c, pr: pr.update(merged_at="soon"),
    lambda c, pr: c["validation"].update(verification_kind="vibes"),
])
def test_unreadable_resolution_inputs_stay_pending(change):
    c, pr = linked()
    change(c, pr)
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"


def test_missing_receipt_stays_pending():
    c, pr = linked()
    assert rw.verify_resolution(c, pr, None, DAY).status == "pending"


def test_closed_unmerged_pr_without_a_reason_is_still_rejected():
    c, pr = linked()
    pr.update(merged=False)
    result = rw.verify_resolution(c, pr, live_receipt(), DAY)
    assert result.status == "rejected" and result.reason


def test_miner_receipt_cannot_prove_a_catalog_search_postcondition():
    c, pr = linked()
    assert rw.verify_resolution(c, pr, mined_receipt(query="model123x"), DAY).status == "pending"


def test_delivery_evidence_keeps_original_provenance_and_inputs_unchanged():
    c, pr = linked()
    before, pr_before = deepcopy(c), deepcopy(pr)
    result = rw.verify_resolution(c, pr, live_receipt(), DAY)
    assert result.evidence["source"] == "ga4 search_empty"
    assert result.evidence["window"] == {"start": "2026-10-07", "end": "2026-11-04"}
    assert result.evidence["metrics"] == {"searches": 1, "zero_result_searches": 1}
    assert result.evidence["pr_url"] == pr["url"]
    assert c == before and pr == pr_before


def test_closed_pr_with_unreadable_merge_flag_is_not_rejected():
    c, pr = linked()
    del pr["merged"]
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"


def test_existing_linked_work_on_an_unlinked_status_is_reconciled_not_duplicated():
    c = candidate(status="validated")
    c["validation"] = validation()
    c["linked_work"] = ["https://github.com/o/r/pull/9"]
    p = rw.plan_work(queue(c), [], DAY, remote_complete=True)
    assert p.action == "reconcile" and p.work.linked_work == ("https://github.com/o/r/pull/9",)


def test_linked_work_must_be_a_list_not_a_substring_match():
    c, pr = linked()
    c["linked_work"] = "https://github.com/o/r/pull/12"
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(status=["new"]),
    lambda c: c.update(term=12345),
    lambda c: c.update(history=5),
    lambda c: c.update(linked_work=5),
    lambda c: c.update(first_seen="20261105"),
])
def test_malformed_candidate_fields_defer_without_raising(mutate):
    c = candidate()
    mutate(c)
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).action == "defer"


@pytest.mark.parametrize("fields", [{"state": {}}, {"started_on": "20261105"},
                                    {"window": {"start": "x"}}, {"metrics": {}}, {"source": 5}])
def test_malformed_receipt_fields_defer_without_raising(fields):
    c = candidate()
    assert rw.plan_work(queue(c), [reserve(c, **fields)], DAY, remote_complete=True).action == "defer"


def test_future_last_attempt_only_reconciles():
    c = candidate()
    receipt = reserve(c, last_attempt_on="2026-11-07")
    assert rw.plan_work(queue(c), [receipt], "2026-11-06", remote_complete=True).action == "reconcile"


@pytest.mark.parametrize("change", [
    lambda c, pr, r: c["validation"].update(verification_kind={"x": 1}),
    lambda c, pr, r: c["validation"].update(term_key=1),
    lambda c, pr, r: r.update(query=1),
    lambda c, pr, r: [c.update(term="!!!"), c["validation"].update(term_key=""), r.pop("query")],
])
def test_malformed_resolution_fields_stay_pending_without_raising(change):
    c, pr = linked()
    receipt = live_receipt()
    change(c, pr, receipt)
    assert rw.verify_resolution(c, pr, receipt, DAY).status == "pending"


def test_existing_work_keeps_the_provenance_snapshot_of_its_reservation():
    c = candidate()
    receipt = reserve(c, source="ga4 search_empty", window={"start": "2026-10-07", "end": "2026-11-04"},
                      metrics={"searches": 1, "zero_result_searches": 1})
    c.update(window={"start": "2026-10-09", "end": "2026-11-06"}, searches=3, zero_result_searches=2)
    p = rw.plan_work(queue(c), [receipt], "2026-11-06", remote_complete=True)
    assert p.action == "resume"
    assert p.work.window == {"start": "2026-10-07", "end": "2026-11-04"}
    assert p.work.metrics == {"searches": 1, "zero_result_searches": 1}
