"""The daily runner lands an autonomous RECONCILE closure (SPEC-demand-work-consumer.md, Required
execution path step 4): both docs/demand bookkeeping files join the publication, the miner's
revision is the observation's mined_revision, and the second PAM pass also follows a closure.

Same discipline as test_demand_run.py: git/gh are recorders and the miner is a fake writing the
REAL 2026-11-06 snapshot and the frozen real queue into the worktree.

Run: cd jr && python3 -m pytest test_demand_run_closure.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import demand_run
import pam_leads
import pam_run
import research_work as rw
from test_demand_broker import SLUG, snapshot_miner, staged, without_unresolved
from test_demand_closure import (KEELOQ_KEY, KEY, MERGE_SHA, NEXT_NOW, PAM_RAW, QUEUE_RAW, RECEIPTS_RAW,
                                 REFS, SNAP, BRANCH, PR_URL, pr_view)
from test_demand_run import git_ok, recorder

QUEUE_PATH = "docs/demand/research-queue.json"
RECEIPTS_PATH = "docs/demand/work-receipts.json"
DEMAND_PR = "https://github.com/fcavalcantirj/esp-atlas/pull/1502"


def tree(root):
    d = root / "docs" / "demand"
    d.mkdir(parents=True)
    (d / "research-queue.json").write_bytes(QUEUE_RAW)
    (d / "work-receipts.json").write_bytes(RECEIPTS_RAW)
    (d / "pam-leads.json").write_bytes(PAM_RAW)
    return root


def gh_all():
    listed = json.dumps([{"headRefName": BRANCH, "url": PR_URL, "state": "MERGED", "number": 1476}])
    return recorder({REFS: (0, json.dumps([{"ref": f"refs/heads/{BRANCH}"}])),
                     ("pr", "list", "--head", BRANCH): (0, listed),
                     ("pr", "list", "--head"): (0, "[]"),
                     ("pr", "view"): (0, pr_view()),
                     ("pr", "create"): (0, DEMAND_PR + "\n"),
                     ("pr", "list"): (0, "[]")})


def pam_unchanged(root, *, now):
    return pam_run.RefreshResult("unchanged", leads=19, potential_gaps=8)


def run(root, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_all())
    kw.setdefault("miner", snapshot_miner(SNAP, queue=json.loads(QUEUE_RAW)))
    return demand_run.run(now=NEXT_NOW, root=root, repo_slug=SLUG, python="/venv/bin/python", **kw)


def receipts(root):
    return json.loads((root / RECEIPTS_PATH).read_text(encoding="utf-8"))["receipts"]


def test_a_closure_lands_both_bookkeeping_files_in_the_demand_pr(tmp_path):
    root, git, gh = tree(tmp_path), git_ok(), gh_all()
    res = run(root, git=git, gh=gh)
    assert res.aborted == "" and res.published is True
    assert QUEUE_PATH in staged(git) and RECEIPTS_PATH in staged(git)
    assert not any(p.startswith("data/") for p in staged(git))
    queue = json.loads((root / QUEUE_PATH).read_text(encoding="utf-8"))
    assert queue["candidates"]["fnk0104s"]["status"] == "closed"
    assert [r["key"] for r in receipts(root)] == [KEY, KEELOQ_KEY]
    assert f"closed {KEY} (delivered)" in res.work and f"reserved {KEELOQ_KEY}" in res.work
    # the observation's mined_revision is the worktree's base revision (git_ok's rev-parse)
    assert ("merge-base", "--is-ancestor", MERGE_SHA, "abc1234") in [c[-4:] for c in git.calls]
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert f"closed {KEY}" in create[create.index("--body") + 1]


def test_an_unchanged_demand_day_still_lands_a_closure(tmp_path):
    root, git = tree(tmp_path), git_ok()
    (root / "docs/demand/2026-11-05.json").write_text(json.dumps({**SNAP, "date": "2026-11-05"}))
    res = run(root, git=git)
    assert res.published is True
    assert QUEUE_PATH in staged(git) and RECEIPTS_PATH in staged(git)


def test_the_second_pam_pass_also_runs_after_a_closure(tmp_path):
    root, git = tree(tmp_path), git_ok()
    res = run(root, git=git, miner=snapshot_miner(without_unresolved(SNAP), queue=json.loads(QUEUE_RAW)),
              pam_refresh=pam_unchanged)
    assert res.published is True and res.aborted == ""
    rows = receipts(root)
    assert rows[0]["key"] == KEY and rows[0]["state"] == "delivered"
    assert len(rows) == 2 and rows[1]["source"] == rw.SOURCE_PAM and rows[1]["started_on"] == "2026-11-07"
    state = pam_run.read_state(root / "docs/demand/pam-leads.json")
    assert rows[1]["key"] in {lead["key"] for lead in pam_leads.candidate_leads(state)}
    assert f"closed {KEY} (delivered)" in res.work and f"reserved {rows[1]['key']}" in res.work
    assert QUEUE_PATH in staged(git) and RECEIPTS_PATH in staged(git)


def test_a_pending_reconcile_publishes_no_bookkeeping(tmp_path):
    root, git = tree(tmp_path), git_ok()
    gh = gh_all()
    stale = recorder({("pr", "view"): (0, pr_view(state="OPEN"))})

    def gh_open(*args):
        return stale(*args) if args[:2] == ("pr", "view") else gh(*args)

    res = run(root, git=git, gh=gh_open)
    assert (root / RECEIPTS_PATH).read_bytes() == RECEIPTS_RAW
    assert json.loads((root / QUEUE_PATH).read_text(encoding="utf-8")) == json.loads(QUEUE_RAW)
    assert RECEIPTS_PATH not in staged(git)
    assert res.work.startswith("reconcile") and "not merged" in res.work


def test_a_broker_error_after_its_writes_still_publishes_them(tmp_path, monkeypatch):
    real = demand_run.demand_broker.reserve

    def writes_then_fails(*args, **kw):
        real(*args, **kw)
        raise RuntimeError("gh vanished during the re-plan")

    monkeypatch.setattr(demand_run.demand_broker, "reserve", writes_then_fails)
    root, git = tree(tmp_path), git_ok()
    (root / "docs/demand/2026-11-05.json").write_text(json.dumps({**SNAP, "date": "2026-11-05"}))
    gh = gh_all()
    res = run(root, git=git, gh=gh)
    assert res.published is True and "broker error RuntimeError" in res.work
    assert RECEIPTS_PATH in staged(git)                  # the queue is staged on every normal publication
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert "Work closed" in create[create.index("--body") + 1]


def test_the_second_pass_after_a_closure_never_closes_again(tmp_path, monkeypatch):
    real, calls = demand_run.demand_broker.reserve, []

    def spy(*args, **kw):
        calls.append(kw)
        return real(*args, **kw)

    monkeypatch.setattr(demand_run.demand_broker, "reserve", spy)
    root = tree(tmp_path)
    run(root, miner=snapshot_miner(without_unresolved(SNAP), queue=json.loads(QUEUE_RAW)),
        pam_refresh=pam_unchanged)
    assert [(c["new_pam"], c.get("close", True)) for c in calls] == [(False, True), (True, False)]


FOREIGN_QUEUE = b'{"version": 1, "candidates": {}, "edited_by": "a concurrent triage"}\n'


def gh_racing_queue(root):
    """gh_all, but a foreign writer edits the research queue while the linked PR is read."""
    gh = gh_all()

    def fn(*args):
        if args[:2] == ("pr", "view"):
            (root / QUEUE_PATH).write_bytes(FOREIGN_QUEUE)
        return gh(*args)

    fn.calls = gh.calls
    return fn


def test_a_cas_refusal_never_lands_a_foreign_queue_edit_as_this_runs_closure(tmp_path):
    root = tree(tmp_path)
    d = demand_run.Decision(SNAP, False, "no-op: demand unchanged since 2026-11-05")
    line = demand_run._reserve_work(root, d, gh_racing_queue(root), NEXT_NOW, SLUG,
                                    git=git_ok(), mined_revision="abc1234")
    assert "changed during the run" in line
    assert (root / QUEUE_PATH).read_bytes() == FOREIGN_QUEUE
    assert d.land is False and d.work_closed is False and d.receipts_changed is False


def test_a_cas_refusal_on_an_unchanged_demand_day_publishes_nothing(tmp_path):
    root, git = tree(tmp_path), git_ok()
    (root / "docs/demand/2026-11-05.json").write_text(json.dumps({**SNAP, "date": "2026-11-05"}))
    gh = gh_racing_queue(root)
    res = run(root, git=git, gh=gh)
    assert res.published is False and "changed during the run" in res.work
    assert not [c for c in gh.calls if c[:2] == ("pr", "create")] and staged(git) == []


def test_a_double_failure_blocks_publication_and_new_work(tmp_path, monkeypatch):
    real_replace, queue_writes = os.replace, []

    def replace(src, dst):
        if Path(dst).name == "work-receipts.json":
            raise OSError("disk full")
        if Path(dst).name == "research-queue.json":
            queue_writes.append(dst)
            if len(queue_writes) > 1:
                raise OSError("read-only")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    root, git, gh = tree(tmp_path), git_ok(), gh_all()
    res = run(root, git=git, gh=gh, pam_refresh=pam_unchanged)
    assert res.published is False and "inconsistent" in res.aborted and KEY in res.aborted
    assert not [c for c in gh.calls if c[:2] == ("pr", "create")] and staged(git) == []
    assert (root / RECEIPTS_PATH).read_bytes() == RECEIPTS_RAW          # no new START, PAM or search


def changed_demand_day(root):
    """A previous snapshot with different demand: the run lands on demand alone (land already True)."""
    (root / "docs/demand/2026-11-05.json").write_text(json.dumps({**SNAP, "date": "2026-11-05", "items": []}))
    return root


def gh_pending_with(gh):
    """gh, but the linked PR is still open: RECONCILE stays pending and the broker writes nothing."""
    stale = recorder({("pr", "view"): (0, pr_view(state="OPEN"))})

    def fn(*args):
        return stale(*args) if args[:2] == ("pr", "view") else gh(*args)

    fn.calls = gh.calls
    return fn


def queue_with_new_candidate():
    queue = json.loads(QUEUE_RAW)
    queue["candidates"]["zz-new-term"] = {**queue["candidates"]["fnk0104s"], "term": "zz-new-term",
                                          "status": "open"}
    return queue


def test_a_cas_refusal_on_a_changed_demand_day_never_stages_the_foreign_queue(tmp_path, monkeypatch):
    seen, real = [], demand_run._publication

    def spy(d, wt_path):
        seen.append(d)
        return real(d, wt_path)

    monkeypatch.setattr(demand_run, "_publication", spy)
    root, git = changed_demand_day(tree(tmp_path)), git_ok()
    gh = gh_racing_queue(root)
    res = run(root, git=git, gh=gh)
    assert res.published is True and "changed during the run" in res.work
    assert seen[0].land is True and seen[0].work_closed is False
    assert QUEUE_PATH not in staged(git) and RECEIPTS_PATH not in staged(git)
    assert "docs/demand/2026-11-06.json" in staged(git) and "docs/demand/unresolved.json" in staged(git)
    assert (root / QUEUE_PATH).read_bytes() == FOREIGN_QUEUE              # foreign bytes left untouched


def test_a_miner_queue_rewrite_is_still_staged_on_a_changed_demand_day(tmp_path):
    root, git = changed_demand_day(tree(tmp_path)), git_ok()
    res = run(root, git=git, gh=gh_pending_with(gh_all()),
              miner=snapshot_miner(SNAP, queue=queue_with_new_candidate()))
    assert res.published is True and res.work.startswith("reconcile")
    assert QUEUE_PATH in staged(git) and RECEIPTS_PATH not in staged(git)
    assert "zz-new-term" in json.loads((root / QUEUE_PATH).read_text(encoding="utf-8"))["candidates"]


def test_a_miner_queue_rewrite_overwritten_by_a_foreign_writer_is_not_staged(tmp_path):
    root, git = changed_demand_day(tree(tmp_path)), git_ok()
    pending = gh_pending_with(gh_all())

    def gh(*args):
        if args[:2] == ("pr", "view"):
            (root / QUEUE_PATH).write_bytes(FOREIGN_QUEUE)
        return pending(*args)

    gh.calls = pending.calls
    res = run(root, git=git, gh=gh, miner=snapshot_miner(SNAP, queue=queue_with_new_candidate()))
    assert res.published is True
    assert QUEUE_PATH not in staged(git) and "docs/demand/2026-11-06.json" in staged(git)
    assert (root / QUEUE_PATH).read_bytes() == FOREIGN_QUEUE
