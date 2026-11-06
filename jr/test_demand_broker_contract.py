"""Additional broker safety oracles; injected remotes only, never real GitHub calls."""
import json

import demand_broker as broker
import research_work as rw
from test_demand_broker import REAL_QUEUE, REAL_SNAPSHOT, REFS, SLUG, gh_remote, recorder


DAY = "2026-11-05"


def demand_dir(tmp_path):
    (tmp_path / "research-queue.json").write_text(json.dumps(REAL_QUEUE))
    return tmp_path


def remote_with_pr(branch, url, state):
    return recorder({
        REFS: (0, json.dumps([{"ref": "refs/heads/" + branch}])),
        ("pr", "list", "--head", branch):
            (0, json.dumps([{"headRefName": branch, "url": url, "state": state, "number": 7}])),
        ("pr", "list", "--head"): (0, "[]"),
    })


def test_unassociated_open_remote_work_is_recovered_or_deferred_before_new_reservation(tmp_path):
    path = demand_dir(tmp_path)
    branch = rw.branch_for(rw.work_key("otherboard123x", "2026-11-01"))
    gh = remote_with_pr(branch, "https://example.test/pull/other", "OPEN")
    result = broker.reserve(path, REAL_SNAPSHOT, gh=gh, today=DAY, repo_slug=SLUG)
    assert result.action in ("defer", "reconcile") and result.changed is False
    assert not (path / broker.RECEIPTS_NAME).exists()


def test_unknown_receipt_version_is_preserved_without_new_work(tmp_path):
    path = demand_dir(tmp_path)
    receipts = path / broker.RECEIPTS_NAME
    original = json.dumps({"version": 999, "receipts": []}).encode()
    receipts.write_bytes(original)
    result = broker.reserve(path, REAL_SNAPSHOT, gh=gh_remote(), today=DAY, repo_slug=SLUG)
    assert result.action == "defer" and result.changed is False
    assert receipts.read_bytes() == original


def test_known_closed_work_does_not_permanently_block_the_next_candidate(tmp_path):
    path = demand_dir(tmp_path)
    pilot = REAL_QUEUE["candidates"]["es3c28p"]
    branch = rw.branch_for(rw.work_key(pilot["term"], rw.opened_on(pilot)))
    gh = remote_with_pr(branch, pilot["linked_work"][0], "MERGED")
    result = broker.reserve(path, REAL_SNAPSHOT, gh=gh, today=DAY, repo_slug=SLUG)
    assert result.action == "start" and result.changed is True
    assert result.key == rw.work_key("fnk0104s", "2026-11-03")
