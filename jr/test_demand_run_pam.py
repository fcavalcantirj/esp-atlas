"""Existing daily CLI -> PAM persistence -> bounded publication; all sources injected."""
import json
from pathlib import Path

import demand_run
import pam_run
from test_demand_broker import (NOW, REAL_QUEUE, REAL_SNAPSHOT, SLUG, gh_remote,
                                snapshot_miner, staged, without_unresolved)
from test_demand_run import Proc, git_ok
from test_pam_leads import Fetch


SNAP = without_unresolved(REAL_SNAPSHOT)
DAY = SNAP["date"]


def tree(root):
    board = root / "data/boards/vendor/example/board.md"
    board.parent.mkdir(parents=True)
    board.write_text('---\nid: example\nname: ES3C28P\n---\n')
    directory = root / "docs/demand"
    directory.mkdir(parents=True)
    (directory / "research-queue.json").write_text(json.dumps(REAL_QUEUE, indent=1))
    return root


def previous(root):
    (root / "docs/demand/2026-11-04.json").write_text(json.dumps({**SNAP, "date": "2026-11-04"}))


def pam_ok(root, *, now):
    return pam_run.refresh_worktree(root, now=now, fetch=Fetch())


def pam_failed(root, *, now):
    return pam_run.RefreshResult("deferred", error="controlled PAM source failure")


def run(root, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_remote())
    kw.setdefault("miner", snapshot_miner(SNAP))
    kw.setdefault("pam_refresh", pam_ok)
    return demand_run.run(now=NOW, root=root, repo_slug=SLUG, python="/venv/bin/python", **kw)


def assert_pam_only_publication(git, *, reservation=False):
    # publish.py also records its normal proposal-ledger bookkeeping.
    paths = set(staged(git))
    assert pam_run.STATE_PATH in paths
    allowed = {pam_run.STATE_PATH, "jr/proposed_ledger.json"}
    if reservation:
        allowed.add("docs/demand/work-receipts.json")
    assert paths <= allowed


def test_fresh_demand_and_pam_changed_paths_share_the_daily_publication(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git)
    assert result.published and not result.aborted
    assert pam_run.STATE_PATH in staged(git)
    assert f"docs/demand/{DAY}.json" in staged(git)
    assert not any(path.startswith("data/") for path in staged(git))
    assert "PAM updated" in result.line()


def test_pam_change_and_its_first_reservation_land_when_search_demand_is_a_noop(tmp_path):
    root, git = tree(tmp_path), git_ok()
    previous(root)
    result = run(root, git=git)
    assert result.published
    assert_pam_only_publication(git, reservation=True)
    receipt = json.loads((root / "docs/demand/work-receipts.json").read_text())["receipts"][0]
    assert receipt["source"] == "pam_feed" and receipt["term"] == "ES3N28P"
    assert "PAM updated" in result.line()


def test_unchanged_pam_and_noop_search_do_not_publish(tmp_path):
    root, git = tree(tmp_path), git_ok()
    previous(root)
    run(root)  # first run discovers/reserves the lead; the replay changes nothing
    before = (root / pam_run.STATE_PATH).read_bytes()
    def unchanged(path, *, now):
        return pam_run.refresh_worktree(path, now=now, fetch=Fetch(statuses={"products": [304], "specs": [304]}))
    result = run(root, git=git, pam_refresh=unchanged)
    assert not result.published and staged(git) == []
    assert (root / pam_run.STATE_PATH).read_bytes() == before
    assert "PAM unchanged" in result.line()


def test_pam_failure_preserves_successful_gsc_publication(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, pam_refresh=pam_failed)
    assert result.published and not result.aborted and not result.source_error
    assert pam_run.STATE_PATH not in staged(git)
    assert f"docs/demand/{DAY}.json" in staged(git)
    assert "PAM deferred" in result.line()


def test_empty_gsc_publishes_successful_pam_without_an_empty_steer(tmp_path):
    root, git = tree(tmp_path), git_ok()
    previous(root)
    before = (root / "docs/demand/2026-11-04.json").read_bytes()
    result = run(root, git=git, miner=snapshot_miner({**SNAP, "items": [], "count": 0}))
    assert result.published
    assert_pam_only_publication(git)
    assert result.source_error and "no demand items" in result.source_error
    assert not (root / f"docs/demand/{DAY}.json").exists()
    assert (root / "docs/demand/2026-11-04.json").read_bytes() == before


def test_failed_gsc_partial_writes_are_restored_before_pam_only_publication(tmp_path):
    root, git = tree(tmp_path), git_ok()
    previous(root)
    queue_path = root / "docs/demand/research-queue.json"
    before = queue_path.read_bytes()
    def failed(path, **kwargs):
        (path / f"docs/demand/{DAY}.json").write_text('{"items": []}')
        queue_path.write_text('{broken partial queue')
        return Proc(returncode=1, stderr="controlled GSC failure")
    result = run(root, git=git, miner=failed)
    assert result.published
    assert_pam_only_publication(git)
    assert result.source_error and "miner failed" in result.line()
    assert queue_path.read_bytes() == before
    assert not (root / f"docs/demand/{DAY}.json").exists()


def test_failed_gsc_and_pam_do_not_publish_or_hide_the_miner_failure(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, miner=lambda *a, **kw: Proc(returncode=1, stderr="GSC failure"),
                 pam_refresh=pam_failed)
    assert not result.published and "miner failed" in result.aborted
    assert staged(git) == []


def test_timeout_abort_does_not_start_more_feed_requests(tmp_path):
    root, calls = tree(tmp_path), []
    def timed_out(*a, **kw):
        raise demand_run.RunAbort("killed by timeout")
    def unexpected(*a, **kw):
        calls.append(True)
        raise AssertionError("PAM must not run after timeout")
    result = run(root, miner=timed_out, pam_refresh=unexpected)
    assert result.aborted == "killed by timeout" and calls == []


def test_updated_pam_manifest_cannot_add_catalog_paths(tmp_path):
    root, git = tree(tmp_path), git_ok()
    def unsafe(*a, **kw):
        return pam_run.RefreshResult("updated", changed_paths=("data/boards/unsafe/board.md",))
    result = run(root, git=git, pam_refresh=unsafe)
    assert result.published and "PAM deferred" in result.line()
    assert not any(path.startswith("data/") for path in staged(git))


def test_timeout_during_pam_aborts_without_publishing(tmp_path):
    root, git = tree(tmp_path), git_ok()
    def timed_out(*a, **kw):
        raise demand_run.RunAbort("killed by timeout")
    result = run(root, git=git, pam_refresh=timed_out)
    assert result.aborted == "killed by timeout" and not result.published
    assert staged(git) == []


def test_timeout_during_broker_does_not_start_pam_or_publish(tmp_path, monkeypatch):
    root, git, calls = tree(tmp_path), git_ok(), []
    def timed_out(*a, **kw):
        raise demand_run.RunAbort("killed by timeout")
    def unexpected(*a, **kw):
        calls.append(True)
        return pam_failed(*a, **kw)
    monkeypatch.setattr(demand_run.demand_broker, "reserve", timed_out)
    result = run(root, git=git, pam_refresh=unexpected)
    assert result.aborted == "killed by timeout" and not result.published
    assert calls == [] and staged(git) == []


def test_pam_and_fnk_reservation_survive_in_the_same_publication(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, miner=snapshot_miner(REAL_SNAPSHOT))
    assert result.published
    assert pam_run.STATE_PATH in staged(git) and "docs/demand/work-receipts.json" in staged(git)
    receipts = json.loads((root / "docs/demand/work-receipts.json").read_text())["receipts"]
    assert len(receipts) == 1 and receipts[0]["term"] == "fnk0104s"


def test_existing_scheduled_cli_enables_pam_without_a_new_flag_or_job(monkeypatch):
    seen = {}
    monkeypatch.setattr(demand_run, "run", lambda **kw: seen.update(kw) or demand_run.RunResult())
    assert demand_run.main([]) == 0
    assert seen["pam_refresh"] is pam_run.refresh_worktree


def test_cli_preserves_primary_source_failure_exit_after_pam_publication(monkeypatch):
    result = demand_run.RunResult(published=True, source_error="controlled miner failure")
    monkeypatch.setattr(demand_run, "run", lambda **kw: result)
    assert demand_run.main([]) == 1


def test_job_receipt_records_runner_and_catalog_revisions(tmp_path):
    result = run(tree(tmp_path))
    assert result.pam_receipt["runner_revision"] == "abc1234"
    assert result.pam_receipt["catalog_revision"] == "abc1234"
