"""Offline contract tests. Signals/receipts are controlled fixtures, never production events."""
from copy import deepcopy

import research_work as rw


DAY = "2026-11-05"


def candidate(term="model123x", status="new"):
    return {"term": term, "status": status, "first_seen": DAY, "last_seen": DAY,
            "classification": "missing_content", "source": "ga4 search_empty",
            "window": {"start": "2026-10-07", "end": "2026-11-04"},
            "searches": 1, "zero_result_searches": 1, "linked_work": [],
            "history": [], "outcome": None, "closed_on": None}


def queue(*rows):
    return {"version": 1, "candidates": {r["term"]: r for r in rows}}


def validation(term="model123x"):
    return {"term_key": term, "identity_verified": True, "validated_by": "fixture-reviewer",
            "verified_on": DAY, "primary_sources": ["https://vendor.example/model123x"],
            "expected_ids": ["vendor-model123x"]}


def reserve(c, **kw):
    plan = rw.plan_work(queue(c), [], DAY, remote_complete=True)
    return {"key": plan.work.key, "branch": plan.work.branch, "started_on": DAY,
            "last_attempt_on": DAY, "state": "reserved", **kw}


def test_closed_pilot_is_an_actual_noop_and_inputs_unchanged():
    c = candidate("es3c28p", "closed")
    c.update(outcome="delivered", closed_on=DAY)
    q = queue(c)
    before = deepcopy(q)
    assert rw.plan_work(q, [], DAY, remote_complete=True).action == "noop"
    assert q == before


def test_new_candidate_means_research_not_permission_to_author():
    p = rw.plan_work(queue(candidate()), [], DAY, remote_complete=True)
    assert p.action == "start" and p.work.phase == "research"
    assert p.work.source == "ga4 search_empty"
    assert p.work.window == {"start": "2026-10-07", "end": "2026-11-04"}


def test_bare_validated_flag_is_not_primary_source_evidence():
    c = candidate(status="validated")
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).work.phase == "research"
    c["validation"] = validation()
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).work.phase == "author"
    c["validation"]["term_key"] = "sibling123x"
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).work.phase == "research"


def test_stable_work_id_normalizes_case_but_never_merges_sibling_models():
    keys = {}
    for term in ("ES3C28P", "es3c28p", "es3n28p", "fnk0104s", "fnk0104a", "fnk0104b"):
        keys[term] = rw.plan_work(queue(candidate(term)), [], DAY, remote_complete=True).work.key
    assert keys["ES3C28P"] == keys["es3c28p"]
    assert len(set(keys.values())) == 5


def test_work_branch_uses_an_opaque_id_not_raw_query_instructions():
    p = rw.plan_work(queue(candidate("model123x; touch /tmp/injected")), [], DAY,
                     remote_complete=True)
    assert p.work.branch.startswith("jr/research-")
    assert "touch" not in p.work.branch and ";" not in p.work.branch


def test_sliding_signal_window_is_not_a_new_work_identity():
    c = candidate()
    original = rw.plan_work(queue(c), [], DAY, remote_complete=True).work.key
    c["window"] = {"start": "2026-10-08", "end": DAY}
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).work.key == original


def test_a_permitted_new_lifecycle_has_a_distinct_work_identity():
    c = candidate()
    original = rw.plan_work(queue(c), [], DAY, remote_complete=True).work.key
    c["history"] = [{"event": "reopened", "date": "2026-12-06"}]
    assert rw.plan_work(queue(c), [], "2026-12-06", remote_complete=True).work.key != original


def test_uncertain_remote_listing_prevents_any_new_or_resumed_execution():
    c = candidate()
    assert rw.plan_work(queue(c), [], DAY, remote_complete=False).action == "defer"
    assert rw.plan_work(queue(c), [reserve(c)], DAY, remote_complete=False).action == "defer"


def test_crash_after_reservation_and_same_day_rerun_only_reconcile():
    c = candidate()
    receipt = reserve(c)
    p = rw.plan_work(queue(c), [receipt], DAY, remote_complete=True)
    assert p.action == "reconcile" and p.work.key == receipt["key"]


def test_remote_work_created_before_local_save_recovers_the_same_work():
    c = candidate()
    receipt = reserve(c, state="proposed", pr_url="https://github.com/o/r/pull/1")
    p = rw.plan_work(queue(c), [receipt], DAY, remote_complete=True)
    assert p.action == "reconcile" and p.work.key == receipt["key"]
    assert p.work.linked_work == (receipt["pr_url"],)


def test_conflicting_remote_prs_for_one_key_are_not_silently_selected():
    c = candidate()
    a = reserve(c, state="proposed", pr_url="https://github.com/o/r/pull/1")
    b = {**a, "pr_url": "https://github.com/o/r/pull/2"}
    p = rw.plan_work(queue(c), [a, b], DAY, remote_complete=True)
    assert p.action == "defer" and "duplicate" in p.reason


def test_closed_work_still_consumes_its_day_budget():
    old = candidate("old123x", "closed")
    receipt = reserve(candidate("old123x"), state="delivered")
    p = rw.plan_work(queue(old, candidate()), [receipt], DAY, remote_complete=True)
    assert p.action == "defer" and "daily" in p.reason


def test_daily_retry_is_bounded_but_an_old_reservation_can_resume_next_day():
    c = candidate()
    p = rw.plan_work(queue(c), [reserve(c)], "2026-11-06", remote_complete=True)
    assert p.action == "resume" and p.work.phase == "research"


def test_existing_linked_work_is_reconciled_even_at_the_cap():
    c = candidate(status="linked")
    c["linked_work"] = ["https://github.com/o/r/pull/1"]
    p = rw.plan_work(queue(c, candidate("next123x")), [reserve(c)], DAY, remote_complete=True)
    assert p.action == "reconcile" and p.work.term == c["term"]


def test_missing_provenance_and_corrupt_receipts_fail_closed():
    c = candidate()
    del c["window"]
    assert rw.plan_work(queue(c), [], DAY, remote_complete=True).action == "defer"
    assert rw.plan_work(queue(candidate()), [{"state": "proposed"}], DAY,
                        remote_complete=True).action == "defer"


def live_receipt(**kw):
    return {"http": 200, "query": "model123x", "ids": ["vendor-model123x"],
            "checked_at": "2026-11-05T12:01:00+00:00", "deployment": "deployed-sha",
            "contains_merge": True, "merge_sha": "merge-sha", **kw}


def linked():
    c = candidate(status="linked")
    c["validation"] = validation()
    c["linked_work"] = ["https://github.com/o/r/pull/1"]
    pr = {"url": c["linked_work"][0], "state": "closed", "merged": True,
          "merge_sha": "merge-sha", "merged_at": "2026-11-05T12:00:00+00:00"}
    return c, pr


def test_merge_and_http_200_with_wrong_sibling_is_not_delivery():
    c, pr = linked()
    before = deepcopy(c)
    assert rw.verify_resolution(c, pr, live_receipt(ids=["vendor-sibling123x"]), DAY).status == "pending"
    assert c == before


def test_expected_result_plus_wrong_sibling_is_not_delivery():
    c, pr = linked()
    receipt = live_receipt(ids=["vendor-model123x", "vendor-sibling123x"])
    assert rw.verify_resolution(c, pr, receipt, DAY).status == "pending"


def test_all_declared_expected_ids_are_required_but_order_is_irrelevant():
    c, pr = linked()
    c["validation"]["expected_ids"] = ["vendor-model123x", "vendor-model123x-rev2"]
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"
    receipt = live_receipt(ids=["vendor-model123x-rev2", "vendor-model123x"])
    assert rw.verify_resolution(c, pr, receipt, DAY).status == "delivered"


def test_explicitly_forbidden_id_cannot_be_validated_as_an_expected_target():
    c, pr = linked()
    c["validation"].update(expected_ids=["vendor-model123x", "vendor-sibling123x"],
                           forbidden_ids=["vendor-sibling123x"])
    receipt = live_receipt(ids=["vendor-model123x", "vendor-sibling123x"])
    assert rw.verify_resolution(c, pr, receipt, DAY).status == "pending"


def test_malformed_additional_search_ids_stay_pending_without_raising():
    c, pr = linked()
    for malformed in (None, {"id": "vendor-sibling123x"}, ["vendor-sibling123x"]):
        receipt = live_receipt(ids=["vendor-model123x", malformed])
        assert rw.verify_resolution(c, pr, receipt, DAY).status == "pending"


def test_stale_deployment_or_verification_before_merge_is_not_delivery():
    c, pr = linked()
    for fields in ({"contains_merge": False}, {"checked_at": "2026-11-05T11:59:00+00:00"},
                   {"http": 503}, {"query": "other123x"}):
        assert rw.verify_resolution(c, pr, live_receipt(**fields), DAY).status == "pending"


def test_only_associated_merged_work_with_exact_live_result_can_close():
    c, pr = linked()
    result = rw.verify_resolution(c, pr, live_receipt(), DAY)
    assert result.status == "delivered" and result.closed_on == DAY
    assert result.evidence["merge_sha"] == "merge-sha"
    assert result.evidence["deployment"] == "deployed-sha"
    assert result.evidence["ids"] == ["vendor-model123x"]
    pr["url"] = "https://github.com/o/r/pull/2"
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"


def test_unreviewed_or_rejected_work_is_never_reported_delivered():
    c, pr = linked()
    pr.update(state="open", merged=False)
    assert rw.verify_resolution(c, pr, live_receipt(), DAY).status == "pending"
    pr.update(state="closed", rejection_reason="source did not establish the model")
    result = rw.verify_resolution(c, pr, live_receipt(), DAY)
    assert result.status == "rejected" and "source" in result.reason


def fnk_linked():
    c, pr = linked()
    c.update(term="fnk0104s", source="gsc_query",
             window={"start": "2026-10-08", "end": "2026-11-05"},
             metrics={"impressions": 22, "clicks": 1, "position": 8.2})
    del c["searches"], c["zero_result_searches"]
    c["validation"].update(term_key="fnk0104s", expected_ids=["freenove-fnk0104s"],
                           verification_kind="demand_resolution")
    return c, pr


def mined_receipt(**kw):
    return {"kind": "demand_resolution", "query": "fnk0104s", "exit_code": 0,
            "resolved": {"board": "freenove-fnk0104s"}, "gap": "COVERED_OK",
            "checked_at": "2026-11-05T12:01:00+00:00", "mined_revision": "fixed-revision",
            "contains_merge": True, "merge_sha": "merge-sha", **kw}


def test_gsc_work_preserves_real_units_without_invented_ga4_searches():
    c, _ = fnk_linked()
    p = rw.plan_work(queue(c), [], DAY, remote_complete=True)
    assert p.work.metrics == {"impressions": 22, "clicks": 1, "position": 8.2}
    assert "searches" not in p.work.metrics and p.work.source == "gsc_query"


def test_fnk_public_search_already_working_cannot_prove_a_miner_fix():
    c, pr = fnk_linked()
    live = live_receipt(query="fnk0104s", ids=["freenove-fnk0104s"])
    assert rw.verify_resolution(c, pr, live, DAY).status == "pending"


def test_fnk_requires_a_fresh_successful_miner_at_the_fixed_revision():
    c, pr = fnk_linked()
    result = rw.verify_resolution(c, pr, mined_receipt(), DAY)
    assert result.status == "delivered"
    assert result.evidence["mined_revision"] == "fixed-revision"
    for fields in ({"exit_code": 1}, {"gap": "UNRESOLVED"},
                   {"resolved": {"board": "freenove-fnk0104a"}}, {"contains_merge": False},
                   {"merge_sha": "different-merge"}, {"mined_revision": None}):
        assert rw.verify_resolution(c, pr, mined_receipt(**fields), DAY).status == "pending"


def test_live_receipt_must_correspond_to_this_merge_and_today():
    c, pr = linked()
    assert rw.verify_resolution(c, pr, live_receipt(merge_sha="different-merge"), DAY).status == "pending"
    assert rw.verify_resolution(c, pr, live_receipt(), "2026-11-06").status == "pending"


# ═══════════ research window (SPEC "Research window", decision 2026-11-12) ═══════════

D2, D3, D4, D5 = "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"


def test_work_without_a_pr_may_run_on_its_start_day_and_the_next():
    c = candidate()
    assert rw.plan_work(queue(c), [reserve(c, last_attempt_on="2026-11-05")], D2,
                        remote_complete=True).action == "resume"


def test_work_without_a_pr_is_exhausted_on_its_third_day_and_frees_its_class():
    """pam-63e3: two days against the same missing source, and the class started nothing else."""
    stuck, nxt = candidate(), candidate("next123x")
    r = reserve(stuck)
    p = rw.plan_work(queue(stuck, nxt), [r], D3, remote_complete=True)
    assert p.action == "start" and p.work.term == "next123x"
    assert p.exhausted == (r["key"],) and r["key"] in p.reason and "human" in p.reason


def test_an_exhausted_item_alone_is_a_noop_that_still_names_it():
    c = candidate()
    r = reserve(c)
    p = rw.plan_work(queue(c), [r], D5, remote_complete=True)
    assert p.action == "noop" and p.exhausted == (r["key"],) and r["key"] in p.reason


def test_work_with_a_pr_or_a_linked_candidate_is_never_exhausted():
    c = candidate()
    pr = reserve(c, state="proposed", pr_url="https://github.com/o/r/pull/1")
    p = rw.plan_work(queue(c), [pr], D5, remote_complete=True)
    assert p.action == "reconcile" and p.exhausted == ()
    linked = candidate(status="linked")
    linked["linked_work"] = ["https://github.com/o/r/pull/1"]
    p = rw.plan_work(queue(linked), [reserve(linked)], D5, remote_complete=True)
    assert p.action == "reconcile" and p.exhausted == ()


def test_retry_on_rearms_one_window():
    c = candidate()
    r = reserve(c, retry_on=D3)
    assert rw.plan_work(queue(c), [r], D3, remote_complete=True).action == "resume"
    assert rw.plan_work(queue(c), [r], D4, remote_complete=True).action == "resume"
    assert rw.plan_work(queue(c), [r], D5, remote_complete=True).exhausted == (r["key"],)


def test_an_unreadable_retry_on_fails_closed():
    c = candidate()
    assert rw.plan_work(queue(c), [reserve(c, retry_on="soon")], D2, remote_complete=True).action == "defer"


def test_launch_state_is_the_one_rule_for_the_launcher():
    c = candidate()
    r = reserve(c, last_attempt_on="2026-11-05")
    assert rw.launch_state(r, "2026-11-05") == "busy"            # attempted today
    assert rw.launch_state(r, D2) == "free"
    assert rw.launch_state(r, D3) == "exhausted"
    assert rw.launch_state({**r, "pr_url": "https://github.com/o/r/pull/1"}, D5) == "busy"
    assert rw.launch_state({**r, "state": "abandoned"}, D2) == "busy"
    assert rw.launch_state({**r, "retry_on": D3}, D3) == "free"
