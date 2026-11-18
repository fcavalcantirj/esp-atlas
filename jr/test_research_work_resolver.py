"""The gauge_gap source (class `resolver`): a vendor × field gap becomes CODE work for the delegate, never a
record (CLAUDE.md "North star", SPEC-demand-work-consumer.md "Resolver work")."""
from __future__ import annotations

import research_work as rw

DAY = "2026-11-18"
PROV = {"vendor": "adafruit", "field": "download_mode", "missing": 20, "records": 26,
        "boards": ["adafruit-feather-esp32-s3", "adafruit-qtpy-esp32-c3", "adafruit-metro-esp32-s3"], "report_date": DAY}


def candidate(status=rw.STATUS_NEW, **extra):
    return {"term": rw.resolver_term(PROV), "source": rw.SOURCE_RESOLVER, "status": status, "first_seen": DAY,
            "history": [], "linked_work": [], "resolver": dict(PROV), **extra}


def test_the_class_key_and_term_are_derived_from_the_row():
    assert rw.class_of(rw.SOURCE_RESOLVER) == rw.CLASS_RESOLVER and rw.CLASS_RESOLVER in rw.CLASSES
    key = rw.resolver_key(PROV)
    assert key.startswith("resolver-") and len(key) == len("resolver-") + 24
    assert rw.resolver_key({**PROV, "boards": ["other"]}) == key                 # the boards never move the key
    assert rw.resolver_key({**PROV, "report_date": "2026-11-19"}) != key          # a later report is a new lifecycle
    assert rw.resolver_term(PROV) == "resolver adafruit download_mode"
    assert rw.candidate_key(candidate()) == key and rw.default_verification_kind(candidate()) == rw.KIND_RESOLVER_LIVE


def test_the_row_shape_fails_closed():
    assert rw.readable_resolver_provenance(PROV)
    for bad in ({**PROV, "field": "pinouts"}, {**PROV, "missing": 0}, {**PROV, "missing": True}, {**PROV, "boards": []},
                {**PROV, "boards": [""]}, {**PROV, "report_date": "yesterday"}, {**PROV, "vendor": ""}, "adafruit", None):
        assert not rw.readable_resolver_provenance(bad), bad
    assert rw.candidate_key(candidate(resolver={**PROV, "boards": []})) is None


def test_the_work_item_carries_the_row_and_no_window_or_metrics():
    w = rw._work(candidate(), [])
    assert w is not None and w.resolver == PROV and w.window is None and w.metrics is None and w.phase == rw.PHASE_RESEARCH
    assert rw._work(candidate(window={"start": DAY, "end": DAY}), []) is None    # a window on code work is unreadable
    receipt = {"key": w.key, "branch": w.branch, "term": w.term, "phase": w.phase, "state": "reserved", "started_on": DAY,
               "source": rw.SOURCE_RESOLVER, "linked_work": [], "resolver": dict(PROV)}
    assert rw._readable_receipt(receipt)
    assert not rw._readable_receipt({**receipt, "resolver": {**PROV, "field": "x"}})
    assert not rw._readable_receipt({**receipt, "key": "resolver-" + "0" * 24})


def test_the_closure_rule_counts_expected_boards_that_gained_the_field():
    problem, fields = rw._KIND_CHECKS[rw.KIND_RESOLVER_LIVE]
    assert set(fields) == {"vendor", "field", "merge_sha", "gained", "verdict"}
    expected = PROV["boards"]
    ok = {"vendor": "adafruit", "field": "download_mode", "merge_sha": "a" * 40, "verdict": "PASS", "gained": expected}
    assert problem(ok, expected, []) is None
    assert problem({**ok, "gained": expected[:2]}, expected, []).startswith("2 of 3 expected boards gained")
    assert problem({**ok, "gained": expected[:1]}, expected[:1], []) is None       # fewer than 3 expected: all of them
    assert "outside the expected set" in problem({**ok, "gained": expected + ["stray-board"]}, expected, [])
    assert problem({**ok, "gained": "all"}, expected, []) == "gained is not a list of board ids"
    assert problem({**ok, "verdict": "PENDING"}, expected, []) is not None
