"""Exact-SKU closure regressions for jr/research_work.py: a sibling in the live result, a partial
expected set or a refreshed queue window must never close work. Controlled fixtures only."""
from copy import deepcopy

import pytest

import research_work as rw
from test_research_work import DAY, linked, live_receipt, queue, reserve


def es3_linked(forbidden=("lcdwiki-es3n28p",)):
    c, pr = linked()
    c["term"] = "es3c28p"
    c["validation"].update(term_key="es3c28p", expected_ids=["lcdwiki-es3c28p"],
                           forbidden_ids=list(forbidden))
    return c, pr


def es3_receipt(ids):
    return live_receipt(query="es3c28p", ids=ids)


def test_expected_id_plus_a_forbidden_sibling_is_not_delivered():
    c, pr = es3_linked()
    before = deepcopy(c)
    result = rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p", "lcdwiki-es3n28p"]), DAY)
    assert result.status == "pending" and "lcdwiki-es3n28p" in result.reason
    assert result.closed_on is None and c == before


def test_complete_expected_set_without_a_forbidden_id_is_delivered():
    c, pr = es3_linked()
    result = rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p"]), DAY)
    assert result.status == "delivered" and result.closed_on == DAY
    assert result.evidence["expected_ids"] == ["lcdwiki-es3c28p"]
    assert result.evidence["forbidden_ids"] == ["lcdwiki-es3n28p"]
    assert result.evidence["ids"] == ["lcdwiki-es3c28p"]


def test_an_undeclared_extra_id_is_not_delivery_either():
    """Exact-SKU work needs exactly the declared set: an id the validation never named may be an
    undeclared sibling, so it leaves the work open just like a forbidden one (SPEC outcome evidence)."""
    c, pr = es3_linked()
    result = rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p", "accessory-case"]), DAY)
    assert result.status == "pending" and "accessory-case" in result.reason


@pytest.mark.parametrize("ids", ["lcdwiki-es3c28p", {"lcdwiki-es3c28p": 1}, None,
                                 ["lcdwiki-es3c28p", 7], ["lcdwiki-es3c28p", ""]])
def test_unreadable_search_ids_stay_pending(ids):
    c, pr = es3_linked()
    assert rw.verify_resolution(c, pr, es3_receipt(ids), DAY).status == "pending"


def test_duplicate_expected_ids_in_the_response_are_still_exactly_the_set():
    c, pr = es3_linked()
    result = rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p", "lcdwiki-es3c28p"]), DAY)
    assert result.status == "delivered"


def test_partial_positive_response_leaves_the_work_open():
    c, pr = es3_linked()
    c["validation"]["expected_ids"] = ["lcdwiki-es3c28p", "lcdwiki-es3c28p-v2"]
    result = rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p"]), DAY)
    assert result.status == "pending" and "lcdwiki-es3c28p-v2" in result.reason


@pytest.mark.parametrize("forbidden", [
    "lcdwiki-es3n28p",                       # not a list
    [""],                                    # unreadable id
    [5],
    ["lcdwiki-es3c28p"],                     # contradicts the expected set
])
def test_unreadable_or_contradictory_forbidden_ids_fail_closed(forbidden):
    c, pr = es3_linked()
    c["validation"]["forbidden_ids"] = forbidden
    assert rw.readable_validation(c) is None
    assert rw.verify_resolution(c, pr, es3_receipt(["lcdwiki-es3c28p"]), DAY).status == "pending"
    c["status"] = "validated"
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).work.phase == "research"


def test_miner_resolving_the_forbidden_sibling_is_not_delivered():
    c, pr = es3_linked()
    c["validation"]["verification_kind"] = "demand_resolution"
    mined = {"kind": "demand_resolution", "query": "es3c28p", "exit_code": 0, "gap": "COVERED_OK",
             "resolved": {"board": "lcdwiki-es3n28p"}, "checked_at": "2026-11-05T12:01:00+00:00",
             "mined_revision": "fixed-revision", "contains_merge": True, "merge_sha": "merge-sha"}
    assert rw.verify_resolution(c, pr, mined, DAY).status == "pending"
    mined["resolved"] = {"board": "lcdwiki-es3c28p"}
    assert rw.verify_resolution(c, pr, mined, DAY).evidence["forbidden_ids"] == ["lcdwiki-es3n28p"]


def refreshed_with_reservation():
    """Linked work whose reservation snapshotted the original signal; the queue has since slid."""
    c, pr = linked()
    original = {"source": "ga4 search_empty", "window": {"start": "2026-10-07", "end": "2026-11-04"},
                "metrics": {"searches": 1, "zero_result_searches": 1}}
    receipt = reserve(c, state="proposed", pr_url=pr["url"], started_on="2026-11-01",
                      last_attempt_on="2026-11-01", **original)
    c.update(window={"start": "2026-10-09", "end": DAY}, searches=3, zero_result_searches=2)
    return c, pr, receipt, original


def test_closure_evidence_keeps_the_reserved_window_and_metrics():
    c, pr, receipt, original = refreshed_with_reservation()
    before, receipt_before = deepcopy(c), deepcopy(receipt)
    result = rw.verify_resolution(c, pr, live_receipt(), DAY, work_receipts=[receipt])
    assert result.status == "delivered"
    assert {f: result.evidence[f] for f in original} == original
    assert c == before and receipt == receipt_before


def test_other_work_receipts_do_not_supply_provenance():
    c, pr, receipt, _ = refreshed_with_reservation()
    other = {**receipt, "key": "0" * 16, "branch": rw.branch_for("0" * 16),
             "window": {"start": "2026-01-01", "end": "2026-01-31"}}
    result = rw.verify_resolution(c, pr, live_receipt(), DAY, work_receipts=[other])
    assert result.evidence["window"] == {"start": "2026-10-09", "end": DAY}


def test_corrupt_work_receipts_leave_the_work_open():
    c, pr, receipt, _ = refreshed_with_reservation()
    corrupt = {**receipt, "window": {"start": "x"}}
    assert rw.verify_resolution(c, pr, live_receipt(), DAY, work_receipts=[corrupt]).status == "pending"
    assert rw.verify_resolution(c, pr, live_receipt(), DAY, work_receipts=[{"state": "x"}]).status == "pending"


def test_unreadable_provenance_cannot_close():
    c, pr = linked()
    del c["window"]
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"
