"""Tests for the demand work reservation the daily runner makes after mining
(SPEC-demand-work-consumer.md, Required execution path step 1 and Idempotence).

Same discipline as test_demand_run.py: `git` and `gh` are recorders, the miner is a fake that
writes into the worktree, so nothing touches a real git/gh, the composio venv or the network.
The GSC row is the REAL committed docs/demand/2026-11-05.json. The queue (closed ES3C28P
candidate) is the real docs/demand/research-queue.json frozen as of that day in
fixtures/demand/: the live file is mutable state the pipeline itself rewrites on every work
branch, so reading it here made these tests flip on whichever work was in flight.

Run: cd jr && python3 -m pytest test_demand_broker.py -v
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import demand_broker
import demand_run
import research_work as rw
from test_demand_run import Proc, git_ok, norm_calls, recorder

REPO = Path(__file__).resolve().parent.parent
DEMAND = REPO / "docs" / "demand"
REAL_SNAPSHOT = json.loads((DEMAND / "2026-11-05.json").read_text(encoding="utf-8"))
REAL_QUEUE = json.loads((REPO / "jr" / "fixtures" / "demand" / "research-queue-2026-11-05.json")
                        .read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc)
SLUG = "fcavalcantirj/esp-atlas"
RECEIPTS = Path("docs/demand") / demand_broker.RECEIPTS_NAME
PR_URL = "https://github.com/fcavalcantirj/esp-atlas/pull/1501"
REFS = ("api", f"repos/{SLUG}/git/matching-refs/heads/{rw.BRANCH_PREFIX}")


def gh_remote(refs="[]", head_prs="[]", refs_rc=0, head_rc=0, open_prs="[]"):
    """A fake gh whose deterministic-branch listing is readable unless told otherwise."""
    return recorder({REFS: (refs_rc, refs),
                     ("pr", "list", "--head"): (head_rc, head_prs),
                     ("pr", "create"): (0, PR_URL + "\n"),
                     ("pr", "list"): (0, open_prs)})


def without_unresolved(snap):
    return {**snap, "items": [it for it in snap["items"] if it["gap"] != "UNRESOLVED"]}


def snapshot_miner(snap=REAL_SNAPSHOT, queue=REAL_QUEUE):
    """Writes exactly the given snapshot + queue into the worktree, as the live miner would."""
    def miner(wt_path: Path, *, python: str, telegram: bool):
        d = wt_path / "docs" / "demand"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{snap['date']}.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
        (d / "unresolved.json").write_text("{}", encoding="utf-8")
        (d / "research-queue.json").write_text(json.dumps(queue, indent=1), encoding="utf-8")
        return Proc(returncode=0)
    return miner


def run(wt, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_remote())
    kw.setdefault("miner", snapshot_miner())
    return demand_run.run(now=NOW, root=wt, repo_slug=SLUG, python="/venv/bin/python", **kw)


def receipts_doc(wt):
    return json.loads((wt / RECEIPTS).read_text(encoding="utf-8"))


def staged(git):
    adds = [c for c in norm_calls(git) if c[:1] == ("add",)]
    return [p for c in adds for p in c[2:]]


FNK_KEY = rw.work_key("fnk0104s", "2026-11-03")      # the snapshot's committed first_seen


# --- the closed pilot ----------------------------------------------------------------------------

def test_closed_es3c28p_yields_no_reservation(tmp_path):
    git = git_ok()
    res = run(tmp_path, git=git, miner=snapshot_miner(without_unresolved(REAL_SNAPSHOT)))
    assert res.aborted == ""
    assert not (tmp_path / RECEIPTS).exists()
    assert str(RECEIPTS) not in staged(git)
    assert res.work.startswith("noop")


# --- the first genuine GSC candidate -------------------------------------------------------------

def test_the_real_gsc_fnk0104s_row_yields_exactly_one_reservation(tmp_path):
    git, gh = git_ok(), gh_remote()
    res = run(tmp_path, git=git, gh=gh)
    assert res.aborted == "" and res.published is True
    receipts = receipts_doc(tmp_path)["receipts"]
    assert len(receipts) == 1
    r = receipts[0]
    assert r["key"] == FNK_KEY and r["branch"] == rw.branch_for(FNK_KEY)
    assert r["term"] == "fnk0104s" and r["phase"] == "research" and r["state"] == "reserved"
    assert r["source"] == "gsc_query"
    assert r["window"] == {"start": "2026-10-08", "end": "2026-11-05"}
    assert r["metrics"] == {"impressions": 22, "clicks": 1, "position": 8.2}
    assert r["started_on"] == "2026-11-05" and r["linked_work"] == []
    assert r["provenance"]["snapshot"] == "docs/demand/2026-11-05.json"
    assert r["provenance"]["opened_on"] == "2026-11-03"
    text = json.dumps(r)
    assert "searches" not in text and "zero_result" not in text            # no invented GA4 counts
    assert str(RECEIPTS) in staged(git)                                       # lands with the demand PR
    assert not any(p.startswith("data/") for p in staged(git))
    creates = [c for c in gh.calls if c[:2] == ("pr", "create")]
    assert len(creates) == 1 and rw.BRANCH_PREFIX not in " ".join(creates[0])   # no PR for the work item
    assert res.work.startswith(f"reserved {FNK_KEY}")


def test_the_receipt_is_readable_by_the_policy_it_feeds(tmp_path):
    run(tmp_path)
    r = receipts_doc(tmp_path)["receipts"][0]
    assert rw._readable_receipt(r)


def test_same_day_rerun_reuses_the_reservation(tmp_path):
    run(tmp_path)
    before = (tmp_path / RECEIPTS).read_bytes()
    git = git_ok()
    res = run(tmp_path, git=git)
    assert (tmp_path / RECEIPTS).read_bytes() == before
    assert [r["key"] for r in receipts_doc(tmp_path)["receipts"]] == [FNK_KEY]
    assert res.work.startswith("reconcile") and FNK_KEY in res.work
    assert str(RECEIPTS) not in staged(git)                                   # unchanged: not re-published


def test_a_crash_after_reserving_recovers_the_same_reservation(tmp_path):
    crashed = run(tmp_path, gh=recorder({REFS: (0, "[]"), ("pr", "list", "--head"): (0, "[]"),
                                         ("pr", "create"): (1, "")}))
    assert crashed.aborted.startswith("publish failed")
    before = (tmp_path / RECEIPTS).read_bytes()
    res = run(tmp_path)
    assert (tmp_path / RECEIPTS).read_bytes() == before                       # no second daily slot
    assert res.work.startswith("reconcile")


def test_next_day_with_the_reservation_committed_takes_no_new_slot(tmp_path):
    run(tmp_path)
    before = (tmp_path / RECEIPTS).read_bytes()
    later = datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)
    res = demand_run.run(now=later, root=tmp_path, repo_slug=SLUG, python="/venv/bin/python",
                         git=git_ok(), gh=gh_remote(), miner=snapshot_miner())
    assert (tmp_path / RECEIPTS).read_bytes() == before
    assert res.work.startswith("resume") and FNK_KEY in res.work


# --- the remote listing ----------------------------------------------------------------------------

@pytest.mark.parametrize("gh", [
    gh_remote(refs_rc=1),                                                    # branch listing failed
    gh_remote(head_rc=1),                                                    # PR listing failed
    gh_remote(head_prs="not json"),                                          # unreadable
    gh_remote(head_prs=json.dumps({"message": "rate limited"})),             # not a listing
    gh_remote(refs=json.dumps([{"ref": "refs/tags/x"}])),                    # not a branch ref
    gh_remote(refs=""),                                                      # empty output is not []
])
def test_an_unreadable_or_truncated_remote_listing_reserves_nothing(tmp_path, gh):
    git = git_ok()
    res = run(tmp_path, git=git, gh=gh)
    assert not (tmp_path / RECEIPTS).exists()
    assert str(RECEIPTS) not in staged(git)
    assert res.work.startswith("defer") and "remote" in res.work


def test_a_listing_that_may_be_truncated_is_incomplete():
    branch = rw.branch_for(FNK_KEY)
    full = [{"headRefName": branch, "url": f"https://x/pull/{i}", "state": "CLOSED"}
            for i in range(demand_broker.PR_LIST_LIMIT)]
    gh = recorder({REFS: (0, "[]"), ("pr", "list", "--head"): (0, json.dumps(full))})
    assert demand_broker.remote_listing(gh, {branch}, SLUG).complete is False
    gh = recorder({REFS: (0, "[][]"), ("pr", "list", "--head"): (0, json.dumps(full[:-1]))})
    remote = demand_broker.remote_listing(gh, {branch}, SLUG)
    assert remote.complete is True and len(remote.prs[branch]) == demand_broker.PR_LIST_LIMIT - 1


def test_the_listing_covers_all_states_of_the_deterministic_branch(tmp_path):
    gh = gh_remote()
    run(tmp_path, gh=gh)
    heads = [c for c in gh.calls if c[:3] == ("pr", "list", "--head")]
    assert heads and all(c[3].startswith(rw.BRANCH_PREFIX) for c in heads)
    assert all(c[c.index("--state") + 1] == "all" for c in heads)
    assert ("pr", "list", "--head", rw.branch_for(FNK_KEY)) in [c[:4] for c in heads]


def test_remote_work_created_before_a_local_save_is_recovered_not_duplicated(tmp_path):
    branch = rw.branch_for(FNK_KEY)
    existing = "https://github.com/fcavalcantirj/esp-atlas/pull/1490"
    listed = json.dumps([{"headRefName": branch, "url": existing, "state": "OPEN", "number": 1490}])
    gh = recorder({REFS: (0, json.dumps([{"ref": f"refs/heads/{branch}"}])),
                   ("pr", "list", "--head", branch): (0, listed),
                   ("pr", "list", "--head"): (0, "[]"),
                   ("pr", "create"): (0, PR_URL + "\n")})
    run(tmp_path, gh=gh)
    r = receipts_doc(tmp_path)["receipts"][0]
    assert r["key"] == FNK_KEY and r["pr_url"] == existing and r["linked_work"] == [existing]
    assert r["provenance"]["remote"] == {"branch": True, "prs": [existing]}
    view = demand_broker.intake(REAL_QUEUE, REAL_SNAPSHOT)
    assert rw.plan_work(view, [r], "2026-11-05", remote_complete=True).action == "reconcile"


# --- the receipts file -----------------------------------------------------------------------------

def test_a_corrupt_receipts_file_is_preserved_and_blocks_new_work(tmp_path):
    path = tmp_path / RECEIPTS
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"version": 1, "receipts": [ trunc')
    git = git_ok()
    res = run(tmp_path, git=git)
    assert path.read_bytes() == b'{"version": 1, "receipts": [ trunc'
    assert str(RECEIPTS) not in staged(git)
    assert res.work.startswith("defer") and "receipts" in res.work


def test_an_unreadable_receipt_entry_is_preserved_too(tmp_path):
    path = tmp_path / RECEIPTS
    path.parent.mkdir(parents=True)
    raw = json.dumps({"version": 1, "receipts": [{"state": "proposed"}]}).encode()
    path.write_bytes(raw)
    run(tmp_path)
    assert path.read_bytes() == raw


def test_other_receipts_and_their_outcomes_are_never_overwritten(tmp_path):
    other_key = rw.work_key("model123x", "2026-10-01")
    other = {"key": other_key, "branch": rw.branch_for(other_key), "term": "model123x",
             "state": "delivered", "started_on": "2026-10-01", "linked_work": ["https://x/pull/7"],
             "pr_url": "https://x/pull/7", "outcome": {"merge_sha": "abc", "verified_on": "2026-10-03"}}
    path = tmp_path / RECEIPTS
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "note": "kept", "receipts": [other]}), encoding="utf-8")
    run(tmp_path)
    doc = receipts_doc(tmp_path)
    assert doc["note"] == "kept"
    assert doc["receipts"][0] == other
    assert [r["key"] for r in doc["receipts"]] == [other_key, FNK_KEY]


def test_a_failed_write_keeps_the_previous_valid_file(tmp_path, monkeypatch):
    path = tmp_path / RECEIPTS
    path.parent.mkdir(parents=True)
    raw = json.dumps({"version": 1, "receipts": []}).encode()
    path.write_bytes(raw)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    git = git_ok()
    res = run(tmp_path, git=git)
    assert path.read_bytes() == raw
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    assert str(RECEIPTS) not in staged(git)
    assert "disk full" in res.work


def test_a_reservation_alone_still_lands_on_an_unchanged_demand_day(tmp_path):
    d = tmp_path / "docs" / "demand"
    d.mkdir(parents=True)
    prev = {**REAL_SNAPSHOT, "date": "2026-11-04"}
    (d / "2026-11-04.json").write_text(json.dumps(prev), encoding="utf-8")
    (d / "research-queue.json").write_text(json.dumps(REAL_QUEUE, indent=1), encoding="utf-8")
    git = git_ok()
    res = run(tmp_path, git=git)
    assert res.published is True
    assert str(RECEIPTS) in staged(git)


def test_the_report_line_names_the_work_decision(tmp_path):
    res = run(tmp_path)
    assert f"work reserved {FNK_KEY}" in res.line()


# --- intake: GSC metrics stay GSC metrics ---------------------------------------------------------

def test_gsc_intake_takes_only_unresolved_gsc_items_in_their_own_units():
    view = demand_broker.intake(REAL_QUEUE, REAL_SNAPSHOT)
    terms = {c["term"]: c for c in view["candidates"].values()}
    assert set(terms) == {"es3c28p", "fnk0104s", "keeloq_mfcodes"}
    fnk = terms["fnk0104s"]
    assert fnk["source"] == "gsc_query" and fnk["status"] == "new" and fnk["first_seen"] == "2026-11-03"
    assert fnk["metrics"] == {"impressions": 22, "clicks": 1, "position": 8.2}
    assert "searches" not in fnk and "zero_result_searches" not in fnk


def test_a_committed_queue_candidate_wins_over_the_same_gsc_term():
    queue = {"version": 1, "candidates": {"fnk0104s": {**REAL_QUEUE["candidates"]["es3c28p"], "term": "fnk0104s"}}}
    view = demand_broker.intake(queue, REAL_SNAPSHOT)
    assert view["candidates"]["fnk0104s"]["status"] == "closed"


def test_intake_never_mutates_the_committed_queue():
    queue = json.loads(json.dumps(REAL_QUEUE))
    demand_broker.intake(queue, REAL_SNAPSHOT)
    assert queue == REAL_QUEUE


def test_paginated_branch_pages_are_read_whole_and_empty_output_is_unreadable():
    assert demand_broker._json_pages('[{"ref": "a"}]\n[{"ref": "b"}]') == [{"ref": "a"}, {"ref": "b"}]
    assert demand_broker._json_pages("[]") == []
    assert demand_broker._json_pages("") is None
    assert demand_broker._json_pages('[{"ref": "a"}] trailing') is None
    assert demand_broker._json_pages('{"message": "Not Found"}') is None


def test_the_demand_pr_body_names_the_reservation(tmp_path):
    gh = gh_remote()
    run(tmp_path, gh=gh)
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    body = create[create.index("--body") + 1]
    assert f"reserved {FNK_KEY}" in body and demand_broker.RECEIPTS_NAME in body


def test_a_broker_failure_never_blocks_the_demand_snapshot(tmp_path, monkeypatch):
    def broken(*a, **kw):
        raise KeyError("boom")

    monkeypatch.setattr(demand_broker, "reserve", broken)
    git = git_ok()
    res = run(tmp_path, git=git)
    assert res.published is True and res.aborted == ""
    assert res.work.startswith("defer: broker error KeyError")
    assert str(RECEIPTS) not in staged(git)


def test_an_open_demand_pr_carrying_receipts_is_never_superseded(tmp_path):
    manifest = {"files": [{"path": "docs/demand/2026-11-04.json", "changeType": "ADDED"},
                          {"path": str(RECEIPTS), "changeType": "ADDED"}], "changedFiles": 2}
    prs = json.dumps([{"number": 1495, "headRefName": "jr/demand-20261104-0930", "labels": [], **manifest}])
    gh = gh_remote(open_prs=prs)
    res = run(tmp_path, gh=gh)
    assert res.published is True and res.superseded == []
    assert not any(c[:2] == ("pr", "close") for c in gh.calls)


def _demand_dir(tmp_path, queue=REAL_QUEUE):
    d = tmp_path / "docs" / "demand"
    d.mkdir(parents=True)
    if queue is not None:
        (d / "research-queue.json").write_text(json.dumps(queue) if isinstance(queue, dict) else queue)
    return d


def test_two_remote_prs_on_one_deterministic_branch_reserve_nothing(tmp_path):
    d, branch = _demand_dir(tmp_path), rw.branch_for(FNK_KEY)
    two = json.dumps([{"headRefName": branch, "url": f"https://x/pull/{n}", "state": "CLOSED"} for n in (1, 2)])
    gh = recorder({REFS: (0, "[]"), ("pr", "list", "--head", branch): (0, two), ("pr", "list", "--head"): (0, "[]")})
    out = demand_broker.reserve(d, REAL_SNAPSHOT, gh=gh, today="2026-11-05", repo_slug=SLUG)
    assert out.action == "defer" and "duplicate" in out.reason and not out.changed
    assert not (d / demand_broker.RECEIPTS_NAME).exists()


def test_an_unreadable_queue_reserves_nothing(tmp_path):
    d = _demand_dir(tmp_path, queue="{ not json")
    out = demand_broker.reserve(d, REAL_SNAPSHOT, gh=gh_remote(), today="2026-11-05", repo_slug=SLUG)
    assert out.action == "defer" and "queue" in out.reason
    assert not (d / demand_broker.RECEIPTS_NAME).exists()


def test_receipts_written_by_someone_else_mid_run_are_never_overwritten(tmp_path):
    d = _demand_dir(tmp_path)
    path = d / demand_broker.RECEIPTS_NAME
    gh = gh_remote()
    racer = json.dumps({"version": 1, "receipts": []})

    def gh_that_races(*args):
        if args[:1] == ("api",):
            path.write_text(racer)
        return gh(*args)

    out = demand_broker.reserve(d, REAL_SNAPSHOT, gh=gh_that_races, today="2026-11-05", repo_slug=SLUG)
    assert out.action == "defer" and "changed during the run" in out.reason
    assert path.read_text() == racer


def test_a_pr_entry_for_another_branch_makes_the_listing_unreadable():
    branch = rw.branch_for(FNK_KEY)
    gh = recorder({REFS: (0, "[]"), ("pr", "list", "--head"): (0, json.dumps([{"headRefName": "main", "url": "u"}]))})
    assert demand_broker.remote_listing(gh, {branch}, SLUG).complete is False
