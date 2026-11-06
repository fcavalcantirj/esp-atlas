"""PAM discovery -> actual shared reservation, using only offline toy feeds/APIs."""
from copy import deepcopy
import json

import pytest

import demand_broker as broker
import pam_leads as pam
import research_work as rw
from test_demand_broker import (REAL_SNAPSHOT, SLUG, gh_remote, without_unresolved)
from test_pam_leads import Fetch, NOW

DAY = "2026-11-06"
NEXT = "2026-11-07"
SNAP = without_unresolved(REAL_SNAPSHOT)
CATALOG = [{"id": "board-c", "name": "ES3C28P"}]


def prepare(path, *, catalog=CATALOG):
    path.mkdir(exist_ok=True)
    (path / "research-queue.json").write_text(json.dumps({"version": 1, "candidates": {}}))
    state = pam.refresh(None, catalog, now=NOW, fetch=Fetch())
    (path / "pam-leads.json").write_text(json.dumps(state))
    return state


def reserve(path, snap=SNAP, **kwargs):
    return broker.reserve(path, snap, gh=kwargs.pop("gh", gh_remote()),
                          today=kwargs.pop("today", DAY), repo_slug=SLUG, **kwargs)


def ledger(path):
    return json.loads((path / broker.RECEIPTS_NAME).read_text())


def test_feed_gap_becomes_research_reservation_with_original_typed_provenance(tmp_path):
    state = prepare(tmp_path)
    result = reserve(tmp_path)
    assert result.action == rw.START and result.phase == rw.PHASE_RESEARCH
    row = ledger(tmp_path)["receipts"][0]
    assert row["key"] == pam.candidate_leads(state)[0]["key"]
    assert row["branch"] == rw.branch_for(row["key"])
    assert row["term"] == "ES3N28P" and row["source"] == "pam_feed"
    assert row["feed"]["checked_at"] == state["checked_at"]
    assert row["feed"]["feeds"] == state["feeds"]
    assert row["candidate"]["feed"] == row["feed"]
    assert row["candidate"]["status"] == "new" and row["linked_work"] == []
    assert "window" not in row and "metrics" not in row
    assert "searches" not in json.dumps(row) and "COPY-ME-NOT" not in json.dumps(row)
    assert rw._readable_receipt(row)


def test_new_search_demand_has_priority_over_earlier_alphabetical_feed_leads(tmp_path):
    prepare(tmp_path, catalog=[])
    result = reserve(tmp_path, REAL_SNAPSHOT)
    assert result.action == rw.START
    row = ledger(tmp_path)["receipts"][0]
    assert row["term"] == "fnk0104s" and row["source"] == "gsc_query"


@pytest.mark.parametrize("day,action", [(DAY, rw.RECONCILE), (NEXT, rw.RESUME)])
def test_replay_recovers_original_feed_work_without_another_budget_slot(tmp_path, day, action):
    prepare(tmp_path)
    first = reserve(tmp_path)
    before = (tmp_path / broker.RECEIPTS_NAME).read_bytes()
    state = json.loads((tmp_path / "pam-leads.json").read_text())
    state["checked_at"] = "2026-11-07T01:00:00Z"
    state["feeds"]["products"]["sha256"] = "b" * 64
    (tmp_path / "pam-leads.json").write_text(json.dumps(state))
    again = reserve(tmp_path, today=day)
    assert again.action == action and again.key == first.key
    assert (tmp_path / broker.RECEIPTS_NAME).read_bytes() == before


@pytest.mark.parametrize("change", ["disappeared", "covered", "corrupt"])
def test_active_feed_work_survives_fresh_lead_list_changes(tmp_path, change):
    state = prepare(tmp_path)
    first = reserve(tmp_path)
    if change == "disappeared":
        state["leads"] = []
    elif change == "covered":
        for lead in state["leads"]:
            lead.update(status="possible_match", matches=["board-n"])
    target = tmp_path / "pam-leads.json"
    target.write_text("{broken" if change == "corrupt" else json.dumps(state))
    result = reserve(tmp_path, REAL_SNAPSHOT)
    assert result.action == rw.RECONCILE and result.key == first.key
    assert len(ledger(tmp_path)["receipts"]) == 1


def test_terminal_semantic_key_is_not_reopened_by_feed_timestamp_changes(tmp_path):
    prepare(tmp_path)
    reserve(tmp_path)
    doc = ledger(tmp_path)
    doc["receipts"][0]["state"] = "rejected"
    (tmp_path / broker.RECEIPTS_NAME).write_text(json.dumps(doc))
    result = reserve(tmp_path, today=NEXT)
    assert result.action == rw.NOOP and len(ledger(tmp_path)["receipts"]) == 1


def test_search_and_feed_work_share_the_single_daily_budget(tmp_path):
    prepare(tmp_path)
    reserve(tmp_path, REAL_SNAPSHOT)
    doc = ledger(tmp_path)
    doc["receipts"][0]["state"] = "delivered"
    (tmp_path / broker.RECEIPTS_NAME).write_text(json.dumps(doc))
    result = reserve(tmp_path)
    assert result.action == rw.DEFER and "daily cap" in result.reason
    assert len(ledger(tmp_path)["receipts"]) == 1


def test_unreadable_remote_state_never_creates_a_feed_reservation(tmp_path):
    prepare(tmp_path)
    result = reserve(tmp_path, gh=gh_remote(refs_rc=1))
    assert result.action == rw.DEFER
    assert not (tmp_path / broker.RECEIPTS_NAME).exists()


def test_feed_branch_created_before_receipt_is_recovered_as_existing_work(tmp_path):
    state = prepare(tmp_path)
    key = pam.candidate_leads(state)[0]["key"]
    branch = rw.branch_for(key)
    url = "https://github.com/fcavalcantirj/esp-atlas/pull/1501"
    remote = gh_remote(refs=json.dumps([{"ref": "refs/heads/" + branch}]),
                       head_prs=json.dumps([{"number": 1501, "url": url,
                                            "headRefName": branch, "state": "OPEN"}]))
    result = reserve(tmp_path, gh=remote)
    assert result.action == rw.START  # durable reservation adopts, never creates the remote PR
    row = ledger(tmp_path)["receipts"][0]
    assert row["key"] == key and row["pr_url"] == url and row["linked_work"] == [url]
    assert not any(call[:2] == ("pr", "create") for call in remote.calls)


def test_feed_reservation_write_failure_preserves_prior_work(tmp_path, monkeypatch):
    prepare(tmp_path, catalog=[])
    reserve(tmp_path)
    doc = ledger(tmp_path)
    doc["receipts"][0]["state"] = "rejected"
    before = json.dumps(doc).encode()
    (tmp_path / broker.RECEIPTS_NAME).write_bytes(before)
    def fail(*args):
        raise OSError("controlled failure")
    monkeypatch.setattr(broker.research_queue, "write_queue", fail)
    result = reserve(tmp_path, today=NEXT)
    assert result.action == rw.DEFER and "write failed" in result.reason
    assert (tmp_path / broker.RECEIPTS_NAME).read_bytes() == before


@pytest.mark.parametrize("search", [False, True])
@pytest.mark.parametrize("corruption", ["broken_json", "unknown_receipt_field", "invalid_etag"])
def test_corrupt_feed_cache_does_not_block_valid_search_work(tmp_path, search, corruption):
    state = prepare(tmp_path)
    if corruption == "unknown_receipt_field":
        state["feeds"]["products"]["metrics"] = {"searches": 99}
    elif corruption == "invalid_etag":
        state["feeds"]["products"]["etag"] = ["not-an-http-header"]
    (tmp_path / "pam-leads.json").write_text("{broken" if corruption == "broken_json" else json.dumps(state))
    result = reserve(tmp_path, REAL_SNAPSHOT if search else SNAP)
    assert result.action == (rw.START if search else rw.DEFER)
    if search:
        assert ledger(tmp_path)["receipts"][0]["source"] == "gsc_query"


def test_exact_search_identity_deduplicates_the_feed_hint(tmp_path):
    state = prepare(tmp_path)
    queue = {"candidates": {"es3n28p": {"term": "ES3N28P", "status": "new",
             "first_seen": DAY, "source": "ga4_site_search", "window": {"start": DAY, "end": DAY},
             "metrics": {"searches": 5, "zero_result_searches": 5}, "linked_work": []}}}
    view = broker.intake(queue, SNAP, pam_state=state)
    assert len(view["candidates"]) == 1
    result = rw.plan_work(view, [], DAY, remote_complete=True)
    assert result.action == rw.START and result.work.source == "ga4_site_search"


def test_feed_authoring_still_requires_primary_source_validation(tmp_path):
    prepare(tmp_path)
    reserve(tmp_path)
    row = ledger(tmp_path)["receipts"][0]
    candidate = row["candidate"]
    candidate["status"] = "validated"
    # The adapter's name/chip hints and even an asserted flag are not evidence.
    candidate["validation"] = {"identity_verified": True}
    plan = rw.plan_work({"candidates": {row["key"]: candidate}}, [], DAY, remote_complete=True)
    assert plan.work.phase == rw.PHASE_RESEARCH


def test_feed_provenance_never_waives_search_source_requirements(tmp_path):
    prepare(tmp_path)
    reserve(tmp_path)
    row = ledger(tmp_path)["receipts"][0]
    candidate = deepcopy(row["candidate"])
    candidate["source"] = "gsc_query"
    result = rw.plan_work({"candidates": {"term": candidate}}, [], DAY, remote_complete=True)
    assert result.action == rw.DEFER
    candidate = deepcopy(row["candidate"])
    candidate["window"] = {"start": DAY, "end": DAY}
    result = rw.plan_work({"candidates": {"term": candidate}}, [], DAY, remote_complete=True)
    assert result.action == rw.DEFER


def test_feed_outcome_preserves_original_provenance_without_search_metrics(tmp_path):
    state = prepare(tmp_path)
    reserve(tmp_path)
    row = ledger(tmp_path)["receipts"][0]
    candidate = deepcopy(row["candidate"])
    url = "https://github.com/fcavalcantirj/esp-atlas/pull/1501"
    candidate.update(status="linked", linked_work=[url], validation={
        "term_key": "es3n28p", "identity_verified": True, "validated_by": "independent-review",
        "verified_on": DAY, "primary_sources": ["https://manufacturer.example/es3n28p"],
        "expected_ids": ["board-n"], "forbidden_ids": ["board-c"]})
    candidate["feed"]["checked_at"] = "2026-11-06T02:00:00Z"
    pr = {"url": url, "merged": True, "merge_sha": "abc123", "merged_at": "2026-11-06T01:00:00Z"}
    observed = {"http": 200, "deployment": "deployment-abc123", "ids": ["board-n"],
                "query": "ES3N28P", "merge_sha": "abc123", "contains_merge": True,
                "checked_at": "2026-11-06T03:00:00Z"}
    result = rw.verify_resolution(candidate, pr, observed, DAY, work_receipts=[row])
    assert result.status == "delivered"
    assert result.evidence["feed"]["checked_at"] == state["checked_at"]
    assert "window" not in result.evidence and "metrics" not in result.evidence


def test_forged_feed_key_or_corrupt_receipt_preserves_state_and_defers(tmp_path):
    prepare(tmp_path)
    reserve(tmp_path)
    doc = ledger(tmp_path)
    doc["receipts"][0]["feed"]["lead"]["source_id"] = "different-sku"
    raw = json.dumps(doc)
    (tmp_path / broker.RECEIPTS_NAME).write_text(raw)
    result = reserve(tmp_path)
    assert result.action == rw.DEFER
    assert (tmp_path / broker.RECEIPTS_NAME).read_text() == raw


@pytest.mark.parametrize("field", ["term", "window", "extra-feed-field"])
def test_malformed_typed_receipts_fail_closed(tmp_path, field):
    prepare(tmp_path)
    reserve(tmp_path)
    doc = ledger(tmp_path)
    row = doc["receipts"][0]
    if field == "term":
        row["term"] = "ES3C28P"
    elif field == "window":
        row["window"] = {"start": DAY, "end": DAY}
    else:
        row["feed"]["feeds"]["products"]["metrics"] = {"searches": 99}
    (tmp_path / broker.RECEIPTS_NAME).write_text(json.dumps(doc))
    assert reserve(tmp_path).action == rw.DEFER
