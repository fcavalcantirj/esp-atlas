"""Autonomous RECONCILE closure in the demand work broker (SPEC-demand-work-consumer.md, Outcome
evidence and Required execution path step 4).

The queue, receipts and PAM state are the REAL docs/demand files as of 2026-11-06 (main ade9d144),
frozen in fixtures/demand/ because the live files are rewritten by the very closure under test.
The snapshot is the real, immutable docs/demand/2026-11-06.json. `gh` and `git` are recorders:
no real GitHub, git or network call is made.

Run: cd jr && python3 -m pytest test_demand_closure.py -v
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import demand_broker as broker
import research_queue
import research_work as rw
from test_demand_broker import REFS, SLUG
from test_demand_run import recorder

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "jr" / "fixtures" / "demand"
QUEUE_RAW = (FIXTURES / "research-queue-2026-11-06.json").read_bytes()
RECEIPTS_RAW = (FIXTURES / "work-receipts-2026-11-06.json").read_bytes()
PAM_RAW = (FIXTURES / "pam-leads-2026-11-06.json").read_bytes()
SNAP = json.loads((REPO / "docs" / "demand" / "2026-11-06.json").read_text(encoding="utf-8"))
FNK_ITEM = next(i for i in SNAP["items"] if i["term"] == "fnk0104s")

KEY = "a721c3339f3d6348"
BRANCH = rw.branch_for(KEY)
PR_URL = "https://github.com/fcavalcantirj/esp-atlas/pull/1476"
MERGE_SHA = "1407ff2ec6bde72753fd22e15bc6c71df49fb713"
MERGED_AT = "2026-11-06T09:19:44Z"
MAIN_SHA = "ade9d14478a87a53c955317f2287b12880f5c9cf"       # the catalog revision this run mined at
KEELOQ_KEY = rw.work_key("keeloq_mfcodes", "2026-11-03")     # the snapshot's only GSC UNRESOLVED item
NEXT_DAY = "2026-11-07"
NEXT_NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
SAME_NOW = datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)
QUEUE, RECEIPTS = research_queue.QUEUE_NAME, broker.RECEIPTS_NAME


def demand_dir(tmp_path, queue=QUEUE_RAW, receipts=RECEIPTS_RAW, pam=PAM_RAW):
    d = tmp_path / "docs" / "demand"
    d.mkdir(parents=True)
    (d / QUEUE).write_bytes(queue)
    (d / RECEIPTS).write_bytes(receipts)
    (d / "pam-leads.json").write_bytes(pam)
    return d


def pr_view(state="MERGED", merge_sha=MERGE_SHA, merged_at=MERGED_AT, url=PR_URL):
    merged = state == "MERGED"
    return json.dumps({"url": url, "state": state, "mergedAt": merged_at if merged else None,
                       "mergeCommit": {"oid": merge_sha} if merged else None})


def gh_for(state="MERGED", view=None, view_rc=0):
    listed = json.dumps([{"headRefName": BRANCH, "url": PR_URL, "state": state, "number": 1476}])
    return recorder({REFS: (0, json.dumps([{"ref": f"refs/heads/{BRANCH}"}])),
                     ("pr", "list", "--head", BRANCH): (0, listed),
                     ("pr", "list", "--head"): (0, "[]"),
                     ("pr", "view"): (view_rc, pr_view(state) if view is None else view)})


def git_for(ancestor_rc=0):
    return recorder({("merge-base", "--is-ancestor"): (ancestor_rc, "")})


def reserve(d, *, gh=None, git=None, snap=SNAP, now=NEXT_NOW, revision=MAIN_SHA, new_pam=True):
    return broker.reserve(d, snap, gh=gh or gh_for(), git=git or git_for(), repo_slug=SLUG,
                          today=now.date().isoformat(), now=now, mined_revision=revision, new_pam=new_pam)


def doc(d, name):
    return json.loads((d / name).read_text(encoding="utf-8"))


def fnk(d):
    return doc(d, QUEUE)["candidates"]["fnk0104s"]


def own_receipt(d, key=KEY):
    return next(r for r in doc(d, RECEIPTS)["receipts"] if r["key"] == key)


def snap_with(**item_fields):
    s = copy.deepcopy(SNAP)
    item = next(i for i in s["items"] if i["term"] == "fnk0104s")
    item.update(item_fields)
    return s


def assert_untouched(d):
    assert (d / QUEUE).read_bytes() == QUEUE_RAW
    assert (d / RECEIPTS).read_bytes() == RECEIPTS_RAW


# --- delivered ----------------------------------------------------------------------------------

def test_the_real_fnk0104s_work_closes_delivered_and_the_next_search_demand_starts(tmp_path):
    d = demand_dir(tmp_path)
    gh, git = gh_for(), git_for()
    out = reserve(d, gh=gh, git=git)

    assert out.closed == KEY and out.resolution == "delivered"
    assert out.action == rw.START and out.key == KEELOQ_KEY and out.phase == rw.PHASE_RESEARCH
    assert out.changed is True and out.queue_changed is True and out.receipts_changed is True
    assert f"closed {KEY} (delivered)" in out.line() and f"reserved {KEELOQ_KEY}" in out.line()

    # the observation came from the injected gh/git, at this run's mined revision
    assert ("pr", "view", PR_URL, "--json", "url,state,mergedAt,mergeCommit") in gh.calls
    assert ("merge-base", "--is-ancestor", MERGE_SHA, MAIN_SHA) in git.calls

    c = fnk(d)
    assert c["status"] == "closed" and c["closed_on"] == NEXT_DAY
    ev = c["outcome"]
    assert ev["pr_url"] == PR_URL and ev["merge_sha"] == MERGE_SHA and ev["merged_at"] == MERGED_AT
    assert ev["verification_kind"] == "demand_resolution" and ev["query"] == "fnk0104s"
    assert ev["mined_revision"] == MAIN_SHA and ev["exit_code"] == 0
    assert ev["resolved"]["board"] == "freenove-fnk0104s" and ev["gap"] == "COVERED_OK"
    assert ev["expected_ids"] == ["freenove-fnk0104s"]
    assert ev["forbidden_ids"] == ["freenove-fnk0104a", "freenove-fnk0104b"]
    assert ev["checked_at"].startswith(NEXT_DAY)
    # closure evidence carries the reservation's original GSC provenance, in GSC units
    assert ev["source"] == "gsc_query" and ev["window"] == {"start": "2026-10-09", "end": "2026-11-06"}
    assert ev["metrics"] == {"impressions": 22, "clicks": 1, "position": 8.2}
    assert c["history"] == [{"event": "closed", "date": NEXT_DAY, "resolution": "delivered", "work": KEY,
                             "pr_url": PR_URL, "merge_sha": MERGE_SHA,
                             "snapshot": "docs/demand/2026-11-06.json"}]
    original = json.loads(QUEUE_RAW)["candidates"]["fnk0104s"]
    for kept in ("term", "first_seen", "source", "window", "metrics", "validation", "linked_work", "evidence"):
        assert c[kept] == original[kept]
    assert doc(d, QUEUE)["candidates"]["es3c28p"] == json.loads(QUEUE_RAW)["candidates"]["es3c28p"]

    r = own_receipt(d)
    before = json.loads(RECEIPTS_RAW)["receipts"][0]
    assert r["state"] == "delivered"
    assert r["resolution"]["status"] == "delivered" and r["resolution"]["closed_on"] == NEXT_DAY
    assert r["resolution"]["evidence"] == ev
    assert {k: v for k, v in r.items() if k not in ("state", "resolution")} == \
           {k: v for k, v in before.items() if k != "state"}            # provenance/attempt/links intact


def test_the_next_start_obeys_every_gate(tmp_path):
    d = demand_dir(tmp_path)
    reserve(d)
    receipts = doc(d, RECEIPTS)["receipts"]
    assert [r["key"] for r in receipts] == [KEY, KEELOQ_KEY]               # one new row, none deleted
    new = receipts[1]
    assert new["term"] == "keeloq_mfcodes" and new["state"] == "reserved" and new["started_on"] == NEXT_DAY
    assert new["source"] == "gsc_query" and new["phase"] == "research"     # search demand before market leads
    assert new["metrics"] == {"impressions": 13, "clicks": 1, "position": 9.8}
    assert all(r["source"] != rw.SOURCE_PAM for r in receipts)            # no PAM lead jumped the queue
    assert rw._readable_receipt(new)


def test_without_new_pam_the_next_start_is_still_the_search_demand(tmp_path):
    d = demand_dir(tmp_path)
    out = reserve(d, new_pam=False)
    assert out.closed == KEY and out.key == KEELOQ_KEY


def test_a_same_day_closure_still_respects_the_daily_cap(tmp_path):
    d = demand_dir(tmp_path)
    out = reserve(d, now=SAME_NOW)
    assert out.closed == KEY and out.resolution == "delivered" and out.changed is True
    assert out.action == rw.DEFER and "daily cap" in out.reason      # a721 already took 2026-11-06's slot
    assert fnk(d)["status"] == "closed" and fnk(d)["closed_on"] == "2026-11-06"
    assert [r["key"] for r in doc(d, RECEIPTS)["receipts"]] == [KEY]


def test_when_nothing_else_is_eligible_the_closure_still_lands(tmp_path):
    d = demand_dir(tmp_path)
    snap = {**SNAP, "items": [i for i in SNAP["items"] if i["gap"] != "UNRESOLVED"]}
    out = reserve(d, snap=snap, new_pam=False)
    assert out.closed == KEY and out.action == rw.NOOP and out.changed is True
    assert out.receipts_changed and out.queue_changed


def test_history_is_appended_never_rewritten(tmp_path):
    queue = json.loads(QUEUE_RAW)
    prior = {"event": "validated", "date": "2026-11-06", "by": "dasbrow_brains"}
    queue["candidates"]["fnk0104s"]["history"] = [prior]
    d = demand_dir(tmp_path, queue=(json.dumps(queue, indent=1) + "\n").encode())
    reserve(d)
    history = fnk(d)["history"]
    assert history[0] == prior and len(history) == 2
    assert history[1]["event"] == "closed" and history[1]["resolution"] == "delivered"


# --- pending: nothing is written -----------------------------------------------------------------

@pytest.mark.parametrize("snap, why", [
    ({**SNAP, "items": [i for i in SNAP["items"] if i["term"] != "fnk0104s"]}, "no item"),
    (snap_with(gap="UNRESOLVED"), "COVERED_OK"),
    (snap_with(resolved={**FNK_ITEM["resolved"], "board": "freenove-fnk0104a"}), "freenove-fnk0104a"),
])
def test_a_snapshot_that_does_not_prove_the_resolution_stays_pending(tmp_path, snap, why):
    d = demand_dir(tmp_path)
    out = reserve(d, snap=snap)
    assert_untouched(d)
    assert out.action == rw.RECONCILE and out.key == KEY and not out.changed and not out.closed
    assert why in out.reason


@pytest.mark.parametrize("ancestor_rc", [1, 128])            # not an ancestor / unknown: never true
def test_a_revision_without_the_merge_stays_pending(tmp_path, ancestor_rc):
    d = demand_dir(tmp_path)
    out = reserve(d, git=git_for(ancestor_rc))
    assert_untouched(d)
    assert out.action == rw.RECONCILE and not out.changed and "merge" in out.reason


def test_an_unmerged_pr_stays_pending(tmp_path):
    d = demand_dir(tmp_path)
    out = reserve(d, gh=gh_for(state="OPEN"))
    assert_untouched(d)
    assert out.action == rw.RECONCILE and not out.changed and "not merged" in out.reason


@pytest.mark.parametrize("view, rc", [("not json", 0), (pr_view(), 1), (pr_view(url="https://x/pull/9"), 0),
                                      (json.dumps({"url": PR_URL, "state": "DRAFT"}), 0)])
def test_an_unreadable_pr_stays_pending(tmp_path, view, rc):
    d = demand_dir(tmp_path)
    out = reserve(d, gh=gh_for(view=view, view_rc=rc))
    assert_untouched(d)
    assert out.action == rw.RECONCILE and not out.changed and "PR" in out.reason


def test_no_mined_revision_means_no_miner_observation(tmp_path):
    d = demand_dir(tmp_path)
    out = reserve(d, revision=None)
    assert_untouched(d)
    assert out.action == rw.RECONCILE and "miner" in out.reason


def test_catalog_search_work_is_never_closed_by_an_invented_live_search(tmp_path):
    queue = json.loads(QUEUE_RAW)
    queue["candidates"]["fnk0104s"]["validation"]["verification_kind"] = "catalog_search"
    d = demand_dir(tmp_path, queue=(json.dumps(queue, indent=1) + "\n").encode())
    before = (d / QUEUE).read_bytes()
    out = reserve(d)
    assert (d / QUEUE).read_bytes() == before and (d / RECEIPTS).read_bytes() == RECEIPTS_RAW
    assert out.action == rw.RECONCILE and not out.changed and "catalog_search" in out.reason


# --- rejected ------------------------------------------------------------------------------------

def test_a_pr_closed_unmerged_is_recorded_rejected_never_delivered(tmp_path):
    d = demand_dir(tmp_path)
    out = reserve(d, gh=gh_for(state="CLOSED"))
    assert out.closed == KEY and out.resolution == "rejected" and out.changed is True
    c = fnk(d)
    assert c["status"] == "closed" and c["closed_on"] == NEXT_DAY
    assert c["outcome"]["status"] == "rejected" and c["outcome"]["pr_url"] == PR_URL
    assert "delivered" not in json.dumps(c)
    assert c["history"][-1]["event"] == "closed" and c["history"][-1]["resolution"] == "rejected"
    r = own_receipt(d)
    assert r["state"] == "rejected" and r["resolution"]["status"] == "rejected"
    assert r["provenance"] == json.loads(RECEIPTS_RAW)["receipts"][0]["provenance"]


# --- compare-and-swap + atomic writes ------------------------------------------------------------

@pytest.mark.parametrize("raced", [QUEUE, RECEIPTS])
def test_a_concurrent_write_to_either_file_leaves_both_untouched(tmp_path, raced):
    d = demand_dir(tmp_path)
    gh = gh_for()
    racer = b'{"version": 1, "raced": true}\n'

    def gh_that_races(*args):
        if args[:2] == ("pr", "view"):
            (d / raced).write_bytes(racer)
        return gh(*args)

    out = reserve(d, gh=gh_that_races)
    assert out.action == rw.DEFER and "changed during the run" in out.reason and not out.changed
    assert (d / raced).read_bytes() == racer
    other = RECEIPTS if raced == QUEUE else QUEUE
    assert (d / other).read_bytes() == (RECEIPTS_RAW if other == RECEIPTS else QUEUE_RAW)


def test_a_failed_receipts_write_rolls_the_queue_back(tmp_path, monkeypatch):
    d = demand_dir(tmp_path)
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name == RECEIPTS:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    out = reserve(d)
    assert_untouched(d)
    assert out.action == rw.DEFER and "disk full" in out.reason and not out.changed
    assert not [p for p in d.iterdir() if p.name.endswith(".tmp")]


FOREIGN = b'{"version": 1, "candidates": {}, "edited_by": "a concurrent triage"}\n'


def test_a_rollback_never_overwrites_a_queue_edited_after_the_closure_wrote_it(tmp_path, monkeypatch):
    d = demand_dir(tmp_path)
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name == RECEIPTS:
            (d / QUEUE).write_bytes(FOREIGN)          # another writer lands between our two writes
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    out = reserve(d)
    assert (d / QUEUE).read_bytes() == FOREIGN
    assert (d / RECEIPTS).read_bytes() == RECEIPTS_RAW
    assert out.action == rw.DEFER and not out.changed and not out.closed and not out.queue_changed
    assert "disk full" in out.reason


def test_closure_is_attempted_once_a_rerun_after_closing_does_nothing_new(tmp_path):
    d = demand_dir(tmp_path)
    reserve(d)
    queue, receipts = (d / QUEUE).read_bytes(), (d / RECEIPTS).read_bytes()
    out = reserve(d)
    assert (d / QUEUE).read_bytes() == queue and (d / RECEIPTS).read_bytes() == receipts
    assert not out.closed and out.action == rw.RECONCILE and out.key == KEELOQ_KEY


# --- edges ---------------------------------------------------------------------------------------

def queue_bytes(mutate):
    queue = json.loads(QUEUE_RAW)
    mutate(queue["candidates"]["fnk0104s"])
    return (json.dumps(queue, indent=1, ensure_ascii=False) + "\n").encode()


def test_several_linked_prs_are_never_guessed_between(tmp_path):
    d = demand_dir(tmp_path, queue=queue_bytes(lambda c: c["linked_work"].append("https://x/pull/2")))
    gh = gh_for()
    out = reserve(d, gh=gh)
    assert out.action == rw.RECONCILE and not out.changed and "2 linked PRs" in out.reason
    assert not [c for c in gh.calls if c[:2] == ("pr", "view")]


def test_validated_work_without_a_link_is_not_verified(tmp_path):
    def unlink(c):
        c.update(status="validated", linked_work=[])
    receipts = json.loads(RECEIPTS_RAW)
    del receipts["receipts"][0]["pr_url"]
    receipts["receipts"][0]["linked_work"] = []
    d = demand_dir(tmp_path, queue=queue_bytes(unlink), receipts=json.dumps(receipts).encode())
    gh = gh_for()
    out = reserve(d, gh=gh, now=SAME_NOW)
    assert out.action == rw.RECONCILE and not out.changed and "not linked" in out.reason
    assert not [c for c in gh.calls if c[:2] == ("pr", "view")]


def test_linked_work_without_a_receipt_row_closes_the_queue_only(tmp_path):
    empty = b'{"version": 1, "receipts": []}\n'
    d = demand_dir(tmp_path, receipts=empty)
    snap = {**SNAP, "items": [i for i in SNAP["items"] if i["gap"] != "UNRESOLVED"]}
    out = reserve(d, snap=snap, new_pam=False)
    assert out.closed == KEY and out.resolution == "delivered"
    assert out.queue_changed and not out.receipts_changed
    assert (d / RECEIPTS).read_bytes() == empty
    assert fnk(d)["outcome"]["window"] == {"start": "2026-10-09", "end": "2026-11-06"}


def test_a_failed_queue_write_keeps_both_files(tmp_path, monkeypatch):
    d = demand_dir(tmp_path)
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name == QUEUE:
            raise OSError("read-only")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    out = reserve(d)
    assert_untouched(d)
    assert out.action == rw.DEFER and "read-only" in out.reason and not out.changed


def test_a_failed_receipts_write_restores_a_compact_queue_byte_exactly(tmp_path, monkeypatch):
    compact = json.dumps(json.loads(QUEUE_RAW)).encode()            # not the writer's own format
    d = demand_dir(tmp_path, queue=compact)
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name == RECEIPTS:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    out = reserve(d)
    assert out.action == rw.DEFER and "both previous files kept" in out.reason and not out.changed
    assert (d / QUEUE).read_bytes() == compact and (d / RECEIPTS).read_bytes() == RECEIPTS_RAW


def test_duplicate_prs_on_the_work_branch_defer_the_closure(tmp_path):
    d = demand_dir(tmp_path)
    two = json.dumps([{"headRefName": BRANCH, "url": PR_URL, "state": "CLOSED", "number": 1476},
                      {"headRefName": BRANCH, "url": "https://x/pull/1477", "state": "MERGED", "number": 1477}])
    gh = gh_for(state="CLOSED")
    racing = recorder({("pr", "list", "--head", BRANCH): (0, two)})

    def gh_two(*args):
        return racing(*args) if args[:4] == ("pr", "list", "--head", BRANCH) else gh(*args)

    out = reserve(d, gh=gh_two)
    assert_untouched(d)
    assert out.action == rw.DEFER and "duplicate remote PRs" in out.reason and not out.changed
    assert not [c for c in gh.calls if c[:2] == ("pr", "view")]


def test_close_false_only_reconciles(tmp_path):
    d = demand_dir(tmp_path)
    gh = gh_for()
    out = broker.reserve(d, SNAP, gh=gh, git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                         mined_revision=MAIN_SHA, close=False)
    assert_untouched(d)
    assert out.action == rw.RECONCILE and out.key == KEY and not out.changed
    assert not [c for c in gh.calls if c[:2] == ("pr", "view")]


def test_a_merged_wording_alone_never_proves_the_term(tmp_path):
    # the group's `resolved` describes its first wording, not necessarily this term
    d = demand_dir(tmp_path)
    out = reserve(d, snap=snap_with(term="freenove fnk0104s", raw_terms=["freenove fnk0104s", "FNK0104S"]))
    assert_untouched(d)
    assert out.action == rw.RECONCILE and not out.closed and "no item" in out.reason


def test_an_earlier_outcome_is_kept_in_the_appended_history(tmp_path):
    d = demand_dir(tmp_path, queue=queue_bytes(lambda c: c.update(outcome="adopted controller PR #1476")))
    reserve(d)
    entry = fnk(d)["history"][-1]
    assert entry["previous_outcome"] == "adopted controller PR #1476"
    assert fnk(d)["outcome"]["merge_sha"] == MERGE_SHA


def test_an_option_looking_revision_never_reaches_git(tmp_path):
    d = demand_dir(tmp_path)
    git = git_for()
    out = reserve(d, git=git, revision="--output=/tmp/x")
    assert_untouched(d)
    assert git.calls == [] and out.action == rw.RECONCILE and "miner" in out.reason


def test_a_durable_closure_is_reported_explicitly_even_when_the_re_plan_raises(tmp_path):
    d = demand_dir(tmp_path)
    gh, views = gh_for(), []

    def gh_dies_after_the_closure(*args):
        if args[:2] == ("pr", "view"):
            views.append(args)
        elif views and args[:1] == ("api",):
            raise RuntimeError("gh vanished during the re-plan")
        return gh(*args)

    closures = []
    with pytest.raises(RuntimeError):
        broker.reserve(d, SNAP, gh=gh_dies_after_the_closure, git=git_for(), repo_slug=SLUG, today=NEXT_DAY,
                       now=NEXT_NOW, mined_revision=MAIN_SHA, closures=closures)
    assert [(o.closed, o.resolution, o.queue_changed, o.receipts_changed) for o in closures] == \
           [(KEY, "delivered", True, True)]
    assert fnk(d)["status"] == "closed" and own_receipt(d)["state"] == "delivered"


def test_no_closure_is_reported_when_its_writes_are_refused(tmp_path):
    d = demand_dir(tmp_path)
    gh = gh_for()

    def gh_that_races(*args):
        if args[:2] == ("pr", "view"):
            (d / QUEUE).write_bytes(FOREIGN)
        return gh(*args)

    closures = []
    broker.reserve(d, SNAP, gh=gh_that_races, git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                   mined_revision=MAIN_SHA, closures=closures)
    assert closures == [] and (d / QUEUE).read_bytes() == FOREIGN


# --- an inconsistent pair: closed by a closure, receipt still live -------------------------------

def double_failure(monkeypatch):
    """The receipts write fails, and so does the queue restore after it."""
    real_replace, queue_writes = os.replace, []

    def replace(src, dst):
        if Path(dst).name == RECEIPTS:
            raise OSError("disk full")
        if Path(dst).name == QUEUE:
            queue_writes.append(dst)
            if len(queue_writes) > 1:
                raise OSError("read-only")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    return real_replace


def test_a_double_failure_defers_and_starts_nothing(tmp_path, monkeypatch):
    d = demand_dir(tmp_path)
    double_failure(monkeypatch)
    out = reserve(d)
    assert out.action == rw.DEFER and "restore failed" in out.reason
    assert not out.changed and not out.closed and not out.receipts_changed
    assert fnk(d)["status"] == "closed" and (d / RECEIPTS).read_bytes() == RECEIPTS_RAW


def test_the_next_run_holds_an_inconsistent_pair_instead_of_starting_new_work(tmp_path, monkeypatch):
    d = demand_dir(tmp_path)
    real_replace = double_failure(monkeypatch)
    reserve(d)
    monkeypatch.setattr(os, "replace", real_replace)
    queue, receipts = (d / QUEUE).read_bytes(), (d / RECEIPTS).read_bytes()
    gh = gh_for()
    following = reserve(d, gh=gh)
    assert following.action == rw.DEFER and "inconsistent" in following.reason and KEY in following.reason
    assert not following.changed and following.action != rw.START
    assert (d / QUEUE).read_bytes() == queue and (d / RECEIPTS).read_bytes() == receipts   # nothing clobbered
    assert not [c for c in gh.calls if c[:2] == ("pr", "view")]                         # no second closure


def test_plan_work_blocks_a_closure_whose_receipt_is_still_live():
    queue = json.loads(QUEUE_RAW)
    c = queue["candidates"]["fnk0104s"]
    c.update(status="closed", closed_on=NEXT_DAY,
             history=[{"event": "closed", "date": NEXT_DAY, "resolution": "delivered", "work": KEY}])
    receipts = json.loads(RECEIPTS_RAW)["receipts"]
    plan = rw.plan_work(queue, receipts, NEXT_DAY, remote_complete=True)
    assert plan.action == rw.DEFER and "inconsistent" in plan.reason and KEY in plan.reason
    assert rw.inconsistent_closures(queue, receipts) == [KEY]
    settled = [{**receipts[0], "state": "delivered"}]
    assert rw.inconsistent_closures(queue, settled) == []
    assert rw.plan_work(queue, settled, NEXT_DAY, remote_complete=True).action == rw.NOOP


def test_a_candidate_closed_by_hand_beside_a_live_receipt_is_not_a_closure_pair():
    queue = json.loads(QUEUE_RAW)
    queue["candidates"]["fnk0104s"].update(status="closed", closed_on=NEXT_DAY, outcome="closed by triage")
    receipts = json.loads(RECEIPTS_RAW)["receipts"]
    assert rw.inconsistent_closures(queue, receipts) == []
    assert rw.plan_work(queue, receipts, NEXT_DAY, remote_complete=True).action == rw.NOOP


# --- the bytes a closure owns, and a pair that records a closure on one side only ----------------

def test_a_durable_closure_records_the_exact_bytes_of_each_write(tmp_path):
    d, writes = demand_dir(tmp_path), {}
    out = broker.reserve(d, SNAP, gh=gh_for(), git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                         mined_revision=MAIN_SHA, writes=writes)
    assert out.closed == KEY and out.action == rw.START          # closed, then the re-plan reserved
    assert writes == {QUEUE: (d / QUEUE).read_bytes(), RECEIPTS: (d / RECEIPTS).read_bytes()}


def test_a_refused_closure_records_no_write(tmp_path):
    d, gh, writes = demand_dir(tmp_path), gh_for(), {}

    def gh_that_races(*args):
        if args[:2] == ("pr", "view"):
            (d / QUEUE).write_bytes(FOREIGN)
        return gh(*args)

    broker.reserve(d, SNAP, gh=gh_that_races, git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                   mined_revision=MAIN_SHA, writes=writes)
    assert writes == {}


def closed_pair():
    queue = json.loads(QUEUE_RAW)
    queue["candidates"]["fnk0104s"].update(
        status="closed", closed_on=NEXT_DAY,
        history=[{"event": "closed", "date": NEXT_DAY, "resolution": "delivered", "work": KEY}])
    base = json.loads(RECEIPTS_RAW)["receipts"]
    settled = [{**base[0], "state": "delivered", "resolution": {"status": "delivered", "closed_on": NEXT_DAY}}]
    return queue, settled, base


def test_a_closure_recorded_on_both_sides_is_consistent():
    queue, settled, base = closed_pair()
    assert rw.one_sided_closures(queue, settled, base) == []


def test_a_settled_receipt_needs_its_closure_in_the_queue():
    _, settled, base = closed_pair()
    assert rw.one_sided_closures(json.loads(FOREIGN), settled, base) == [KEY]
    assert rw.one_sided_closures(json.loads(QUEUE_RAW), settled, base) == [KEY]


def test_a_closed_candidate_needs_its_settled_receipt():
    queue, _, base = closed_pair()
    assert rw.one_sided_closures(queue, [], base) == [KEY]                 # the receipt vanished
    assert rw.one_sided_closures(queue, base, base) == [KEY]               # the receipt is still live


def test_a_closure_without_a_receipt_and_a_reopened_candidate_stay_consistent():
    queue, settled, base = closed_pair()
    assert rw.one_sided_closures(queue, [], []) == []                     # no receipt to settle
    c = queue["candidates"]["fnk0104s"]
    c.update(status="open", history=[*c["history"], {"event": "reopened", "date": "2026-12-08"}])
    assert rw.one_sided_closures(queue, settled, base) == []              # its closure stays in history


def test_the_bytes_wrapper_reads_the_pair_and_refuses_nothing_unreadable():
    queue, settled, base = closed_pair()
    as_bytes = [json.dumps(x).encode() for x in (queue, {"version": 1, "receipts": []}, {"version": 1, "receipts": base})]
    assert broker.one_sided_closures(*as_bytes) == [KEY]
    assert broker.one_sided_closures(b"{not json", as_bytes[1], as_bytes[2]) == []


# --- the re-plan after a closure never builds on a foreign writer's bytes -------------------------

def race_after_the_closure(monkeypatch, d, name):
    """A foreign writer edits `name` the moment the closure's writes are durable, before the broker's
    internal re-plan reads the pair. The closed candidate and its settled receipt are kept (no
    one-sided closure gives it away); only a free-text field changes. Returns the foreign bytes."""
    real, foreign = broker._write_closure, []

    def write_then_race(*args, **kw):
        problem = real(*args, **kw)
        if not problem:
            edited = doc(d, name)
            if name == RECEIPTS:
                edited["receipts"][0]["resolution"]["reason"] = "rewritten by a concurrent triage"
            else:
                edited["edited_by"] = "a concurrent triage"
            foreign.append(json.dumps(edited).encode())
            (d / name).write_bytes(foreign[0])
        return problem

    monkeypatch.setattr(broker, "_write_closure", write_then_race)
    return foreign


@pytest.mark.parametrize("name", [RECEIPTS, QUEUE])
def test_a_foreign_edit_before_the_re_plan_is_never_built_on_or_owned(tmp_path, monkeypatch, name):
    d, writes = demand_dir(tmp_path), {}
    foreign = race_after_the_closure(monkeypatch, d, name)
    out = broker.reserve(d, SNAP, gh=gh_for(), git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                         mined_revision=MAIN_SHA, writes=writes)
    assert (d / name).read_bytes() == foreign[0]                   # kept byte-for-byte, nothing appended
    assert KEELOQ_KEY not in {r["key"] for r in doc(d, RECEIPTS)["receipts"]}
    assert out.action == rw.DEFER and out.foreign == (name,) and "another writer" in out.reason
    assert writes[name] != foreign[0]                              # ownership is never handed to them


def test_a_foreign_receipts_edit_during_the_closures_queue_write_is_never_overwritten(tmp_path, monkeypatch):
    """The closure checks both files, then writes the queue: a receipts edit landing during that write
    is preserved, the closure's own queue write is undone, and nothing is recorded as this run's."""
    d, writes = demand_dir(tmp_path), {}
    foreign = b'{"version": 1, "receipts": [], "edited_by": "a concurrent triage"}\n'
    real = research_queue.write_queue

    def write_then_race(doc_, path):
        out = real(doc_, path)
        if Path(path).name == QUEUE:
            (d / RECEIPTS).write_bytes(foreign)
        return out

    monkeypatch.setattr(research_queue, "write_queue", write_then_race)
    out = broker.reserve(d, SNAP, gh=gh_for(), git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                         mined_revision=MAIN_SHA, writes=writes)
    assert (d / RECEIPTS).read_bytes() == foreign
    assert (d / QUEUE).read_bytes() == QUEUE_RAW                   # no closure left on one side
    assert out.action == rw.DEFER and out.closed == "" and writes == {}
