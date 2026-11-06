"""The daily runner lands an autonomous RECONCILE closure (SPEC-demand-work-consumer.md, Required
execution path step 4): both docs/demand bookkeeping files join the publication, the miner's
revision is the observation's mined_revision, and the second PAM pass also follows a closure.

Same discipline as test_demand_run.py: git/gh are recorders and the miner is a fake writing the
REAL 2026-11-06 snapshot and the frozen real queue into the worktree.

Run: cd jr && python3 -m pytest test_demand_run_closure.py -v
"""
from __future__ import annotations

import json

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
    res = run(root, git=git)
    assert res.published is True and "broker error RuntimeError" in res.work
    assert QUEUE_PATH in staged(git) and RECEIPTS_PATH in staged(git)


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
