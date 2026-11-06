"""Broker oracles for remote PR *state* and the receipts schema version
(SPEC-demand-work-consumer.md, Idempotence and failure recovery). Injected remotes only.

Run: cd jr && python3 -m pytest test_demand_broker_remote_state.py -v
"""
from __future__ import annotations

import copy
import json

import pytest

import demand_broker as broker
import research_work as rw
from test_demand_broker import FNK_KEY, REAL_QUEUE, REAL_SNAPSHOT, REFS, SLUG, gh_remote, recorder

DAY = "2026-11-05"
OTHER_TERM = "zzboard9x"                      # sorts after fnk0104s: never the default pick
OTHER_KEY = rw.work_key(OTHER_TERM, "2026-11-01")
OTHER_BRANCH = rw.branch_for(OTHER_KEY)
OTHER_PR = "https://example.test/pull/42"


def queue_with_other():
    q = copy.deepcopy(REAL_QUEUE)
    q["candidates"][OTHER_TERM] = {
        "term": OTHER_TERM, "first_seen": "2026-11-01", "last_seen": "2026-11-04",
        "source": "ga4 search_empty", "window": {"start": "2026-10-07", "end": "2026-11-04"},
        "searches": 2, "zero_result_searches": 2, "status": "new", "linked_work": [], "history": []}
    return q


def demand_dir(tmp_path, queue=None, receipts=None):
    (tmp_path / "research-queue.json").write_text(json.dumps(queue or REAL_QUEUE))
    if receipts is not None:
        (tmp_path / broker.RECEIPTS_NAME).write_bytes(receipts)
    return tmp_path


def gh_with(branch, *prs):
    listed = [{"headRefName": branch, "number": n, "url": url, "state": state} for n, (url, state) in enumerate(prs)]
    return recorder({REFS: (0, json.dumps([{"ref": "refs/heads/" + branch}])),
                     ("pr", "list", "--head", branch): (0, json.dumps(listed)),
                     ("pr", "list", "--head"): (0, "[]")})


def reserve(path, gh):
    return broker.reserve(path, REAL_SNAPSHOT, gh=gh, today=DAY, repo_slug=SLUG)


@pytest.mark.parametrize("state", [None, "", "open", "DRAFT", 1])
def test_a_pr_without_a_readable_state_makes_the_listing_incomplete(state):
    listed = json.dumps([{"headRefName": OTHER_BRANCH, "url": OTHER_PR, "state": state}])
    gh = recorder({REFS: (0, "[]"), ("pr", "list", "--head"): (0, listed)})
    assert broker.remote_listing(gh, {OTHER_BRANCH}, SLUG).complete is False


def test_the_listing_keeps_each_pr_state_not_only_its_url():
    remote = broker.remote_listing(gh_with(OTHER_BRANCH, (OTHER_PR, "OPEN")), set(), SLUG)
    assert remote.complete and remote.prs[OTHER_BRANCH] == [{"url": OTHER_PR, "state": "OPEN", "number": 0}]


@pytest.mark.parametrize("doc", [{"receipts": []}, {"version": True, "receipts": []},
                                 {"version": "1", "receipts": []}, {"version": 2, "receipts": []}])
def test_a_receipts_file_without_the_supported_version_is_refused_and_kept(tmp_path, doc):
    raw = json.dumps(doc).encode()
    path = demand_dir(tmp_path, receipts=raw)
    out = reserve(path, gh_remote())
    assert out.action == rw.DEFER and not out.changed and "version" in out.reason
    assert (path / broker.RECEIPTS_NAME).read_bytes() == raw


def test_an_open_pr_on_another_open_candidate_is_recovered_before_new_work(tmp_path):
    path = demand_dir(tmp_path, queue_with_other())
    out = reserve(path, gh_with(OTHER_BRANCH, (OTHER_PR, "OPEN")))
    assert out.action == rw.START and out.changed and out.key == OTHER_KEY
    r = json.loads((path / broker.RECEIPTS_NAME).read_text())["receipts"][0]
    assert r["pr_url"] == OTHER_PR and r["linked_work"] == [OTHER_PR]
    assert r["provenance"]["remote"] == {"branch": True, "prs": [OTHER_PR]}


def test_an_open_pr_whose_only_receipt_is_terminal_defers_new_work(tmp_path):
    settled = {"key": OTHER_KEY, "branch": OTHER_BRANCH, "term": OTHER_TERM, "state": "abandoned",
               "started_on": "2026-11-01", "pr_url": OTHER_PR, "linked_work": [OTHER_PR]}
    raw = json.dumps({"version": 1, "receipts": [settled]}).encode()
    path = demand_dir(tmp_path, queue_with_other(), receipts=raw)
    out = reserve(path, gh_with(OTHER_BRANCH, (OTHER_PR, "OPEN")))
    assert out.action == rw.DEFER and not out.changed and OTHER_BRANCH in out.reason
    assert (path / broker.RECEIPTS_NAME).read_bytes() == raw


def test_closed_or_merged_work_on_an_unknown_branch_never_blocks(tmp_path):
    path = demand_dir(tmp_path)
    gh = gh_with(OTHER_BRANCH, ("https://example.test/pull/1", "CLOSED"), ("https://example.test/pull/2", "MERGED"))
    out = reserve(path, gh)
    assert out.action == rw.START and out.changed and out.key == FNK_KEY


def test_plan_work_prefers_the_named_branches_among_startable_work():
    view = broker.intake(queue_with_other(), REAL_SNAPSHOT)
    assert rw.plan_work(view, [], DAY, remote_complete=True).work.key == FNK_KEY
    plan = rw.plan_work(view, [], DAY, remote_complete=True, prefer={OTHER_BRANCH})
    assert plan.action == rw.START and plan.work.key == OTHER_KEY
