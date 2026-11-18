"""research_work: the `quote_check` source (class `hygiene`) — a record whose quoted text the cited page does
not hold becomes a work item for the executor (SPEC-demand-work-consumer.md, "Hygiene: quote FAILs").
Offline contract tests; every quote report is a controlled fixture."""
from __future__ import annotations

from copy import deepcopy

import pytest

import research_work as rw

DAY = "2026-11-17"
QUOTE = {"record": "data/boards/m5stack/m5dial/board.md", "id": "m5dial", "report_date": DAY,
         "quotes": ["PORT.A | G13 | G15", "PORT.B | G2 | G1"],
         "urls": ["https://docs.m5stack.com/en/core/M5Dial"]}


def candidate(quote=QUOTE, status="new"):
    return {"term": rw.quote_term(quote), "source": rw.SOURCE_QUOTE, "status": status, "first_seen": quote["report_date"],
            "history": [], "linked_work": [], "snapshot": "docs/demand/quote-report.json", "quote": deepcopy(quote)}


def queue(*rows):
    return {"version": 1, "candidates": {rw.candidate_key(r): r for r in rows}}


def test_the_quote_source_is_its_own_daily_class():
    assert rw.class_of(rw.SOURCE_QUOTE) == rw.CLASS_HYGIENE and rw.CLASS_HYGIENE in rw.CLASSES
    assert rw.class_of(rw.SOURCE_PAM) == rw.CLASS_PAM and rw.class_of("gsc_query") == rw.CLASS_SEARCH


def test_the_work_key_is_the_record_and_the_report_day_never_the_quotes():
    k = rw.quote_key(QUOTE)
    assert k.startswith("fix-") and len(k) == 4 + 24
    assert rw.quote_key({**QUOTE, "quotes": ["other"]}) == k                      # same record, same day: same work
    assert rw.quote_key({**QUOTE, "report_date": "2026-11-20"}) != k               # a later report is a new lifecycle
    assert rw.candidate_key(candidate()) == k


def test_readable_provenance_fails_closed():
    assert rw.readable_quote_provenance(QUOTE)
    for bad in ({**QUOTE, "record": "jr/x.py"}, {**QUOTE, "quotes": []}, {**QUOTE, "report_date": "17/11/2026"},
                {**QUOTE, "id": ""}, {k: v for k, v in QUOTE.items() if k != "urls"}, "not a dict"):
        assert not rw.readable_quote_provenance(bad), bad


def test_a_quote_candidate_plans_as_hygiene_research_with_its_own_provenance():
    plan = rw.plan_work(queue(candidate()), [], DAY, remote_complete=True, source_class=rw.CLASS_HYGIENE)
    assert plan.action == rw.START and plan.work.phase == rw.PHASE_RESEARCH
    assert plan.work.source == rw.SOURCE_QUOTE and plan.work.quote == QUOTE and plan.work.window is None
    assert plan.work.branch == rw.branch_for(rw.quote_key(QUOTE))
    # another class's pass never starts it
    assert rw.plan_work(queue(candidate()), [], DAY, remote_complete=True, source_class=rw.CLASS_PAM).action == rw.NOOP


def test_a_quote_candidate_with_window_or_metrics_or_broken_provenance_is_refused():
    c = candidate()
    c["window"] = {"start": "2026-10-20", "end": DAY}
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True, source_class=rw.CLASS_HYGIENE).action == rw.DEFER
    c = candidate()
    c["quote"]["quotes"] = []
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).action == rw.DEFER


def test_the_validation_kind_and_the_closure_check_for_quote_work():
    assert rw.default_verification_kind(candidate()) == rw.KIND_CATALOG_QUOTE
    problem, fields = rw._KIND_CHECKS[rw.KIND_CATALOG_QUOTE]
    assert set(fields) >= {"record", "merge_sha", "verdict"}
    ok = {"kind": rw.KIND_CATALOG_QUOTE, "record": QUOTE["record"], "id": "m5dial", "merge_sha": "abc", "verdict": "PASS"}
    assert problem(ok, ["m5dial"], []) is None
    assert "FAIL" in problem({**ok, "verdict": "FAIL"}, ["m5dial"], [])
    assert "INCONCLUSIVE" in problem({**ok, "verdict": "INCONCLUSIVE"}, ["m5dial"], [])
    assert problem({**ok, "id": "other"}, ["m5dial"], []) is not None


def test_a_quote_receipt_is_readable_only_with_its_snapshot_and_matching_key():
    c = candidate()
    r = {"key": rw.quote_key(QUOTE), "branch": rw.branch_for(rw.quote_key(QUOTE)), "term": c["term"], "source": rw.SOURCE_QUOTE,
         "state": "reserved", "started_on": DAY, "quote": deepcopy(QUOTE), "candidate": c}
    assert rw._readable_receipt(r)
    assert not rw._readable_receipt({**r, "key": "fix-000000000000000000000000"})
    assert not rw._readable_receipt({**r, "window": {"start": DAY, "end": DAY}})
    assert not rw._readable_receipt({k: v for k, v in r.items() if k != "quote"})
