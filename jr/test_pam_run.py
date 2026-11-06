"""Worktree persistence contract for existing daily-runner integration; no cron changes."""
import datetime as dt
import json

import pytest

import pam_run
import research_queue
from test_pam_leads import Fetch, NOW, feeds


def tree(tmp_path):
    board = tmp_path / "data/boards/vendor/catalog-c/board.md"
    board.parent.mkdir(parents=True)
    board.write_text('---\nid: catalog-c\nname: Example board\naka: [ES3C28P]\n---\n')
    return tmp_path


def run(root, **kwargs):
    return pam_run.refresh_worktree(root, now=NOW, fetch=kwargs.pop("fetch", Fetch()), **kwargs)


def test_refresh_persists_only_minimal_state_with_explicit_publication_path(tmp_path):
    root = tree(tmp_path)
    before = {str(p): p.read_bytes() for p in (root / "data").rglob("*.md")}
    result = run(root)
    assert result.status == "updated"
    assert result.changed_paths == ("docs/demand/pam-leads.json",)
    assert result.leads == 2 and result.potential_gaps == 1
    state = json.loads((root / pam_run.STATE_PATH).read_text())
    assert state == result.state
    assert "COPY-ME-NOT" not in json.dumps(state)
    assert before == {str(p): p.read_bytes() for p in (root / "data").rglob("*.md")}


def test_unchanged_conditional_refresh_has_receipt_but_no_write_or_publication(tmp_path):
    root = tree(tmp_path)
    run(root)
    target = root / pam_run.STATE_PATH
    before = target.read_bytes()
    calls = []
    result = run(root, fetch=Fetch(statuses={"products": [304], "specs": [304]}),
                 writer=lambda *args: calls.append(args))
    assert result.status == "unchanged" and result.changed_paths == ()
    assert target.read_bytes() == before and calls == []
    assert result.receipt["feed_statuses"] == {"products": [304], "specs": [304]}


def test_only_timestamps_moving_does_not_create_daily_bookkeeping_churn(tmp_path):
    root = tree(tmp_path)
    run(root)
    target = root / pam_run.STATE_PATH
    before = target.read_bytes()
    later = NOW + dt.timedelta(days=1)
    result = pam_run.refresh_worktree(root, now=later, fetch=Fetch())
    assert result.status == "unchanged" and target.read_bytes() == before
    assert result.receipt["checked_at"].startswith("2026-11-07")


def test_changed_source_pointer_updates_state_without_copying_spec_value(tmp_path):
    root = tree(tmp_path)
    first = run(root)
    data = feeds()
    data["specs"]["products"][0]["specs"]["flash_mb"]["source"] += "/revision-b"
    second = run(root, fetch=Fetch(data))
    assert second.status == "updated" and second.state != first.state
    assert "COPY-ME-NOT" not in (root / pam_run.STATE_PATH).read_text()


def test_current_catalog_alias_is_rechecked_on_304(tmp_path):
    root = tree(tmp_path)
    run(root)
    board = root / "data/boards/vendor/catalog-n/board.md"
    board.parent.mkdir()
    board.write_text('---\nid: catalog-n\nname: ES3N28P\n---\n')
    result = run(root, fetch=Fetch(statuses={"products": [304], "specs": [304]}))
    assert result.status == "updated" and result.potential_gaps == 0


def test_other_catalog_record_kinds_do_not_cover_a_board_lead(tmp_path):
    root = tree(tmp_path)
    firmware = root / "data/firmware/es3n28p/firmware.md"
    firmware.parent.mkdir(parents=True)
    firmware.write_text('---\nid: es3n28p\nname: ES3N28P\n---\n')
    assert run(root).potential_gaps == 1


def test_feed_failure_is_reported_without_overwriting_last_good_state(tmp_path):
    root = tree(tmp_path)
    run(root)
    target = root / pam_run.STATE_PATH
    before = target.read_bytes()
    result = run(root, fetch=Fetch(statuses={"specs": [503]}))
    assert result.status == "deferred" and not result.changed_paths
    assert target.read_bytes() == before and result.error


@pytest.mark.parametrize("corruption", ["{broken json", "null", "[]", "x" * (pam_run.MAX_STATE_BYTES + 1)])
def test_corrupt_cached_state_is_preserved_and_no_fetch_runs(tmp_path, corruption):
    root = tree(tmp_path)
    target = root / pam_run.STATE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(corruption)
    fetch = Fetch()
    result = run(root, fetch=fetch)
    assert result.status == "deferred" and target.read_text() == corruption
    assert fetch.calls == []


def test_atomic_replace_failure_preserves_old_file_and_removes_temp_file(tmp_path, monkeypatch):
    root = tree(tmp_path)
    run(root)
    target = root / pam_run.STATE_PATH
    before = target.read_bytes()
    data = feeds()
    data["specs"]["products"][0]["specs"]["flash_mb"]["source"] += "/revision-b"
    def fail(*args):
        raise OSError("controlled replace failure")
    monkeypatch.setattr(research_queue.os, "replace", fail)
    result = run(root, fetch=Fetch(data))
    assert result.status == "deferred" and target.read_bytes() == before
    assert list(target.parent.glob(".pam-leads.json.*.tmp")) == []


@pytest.mark.parametrize("destination", ["outside", "catalog"])
def test_symlink_cannot_redirect_state_outside_worktree_or_into_catalog(tmp_path, destination):
    root = tree(tmp_path / "repo")
    real = tmp_path / "outside" if destination == "outside" else root / "data/redirect"
    real.mkdir()
    (root / "docs").mkdir()
    (root / "docs/demand").symlink_to(real, target_is_directory=True)
    result = run(root)
    assert result.status == "deferred"
    assert list(real.iterdir()) == []


def test_missing_or_unreadable_board_catalog_fails_before_network(tmp_path):
    fetch = Fetch()
    assert run(tmp_path, fetch=fetch).status == "deferred"
    assert fetch.calls == []
    root = tree(tmp_path)
    next((root / "data").rglob("board.md")).write_text('---\nname: [invalid\n---\n')
    assert run(root, fetch=fetch).status == "deferred" and fetch.calls == []


def test_json_report_is_bounded_metadata_not_full_lead_state(tmp_path):
    result = run(tree(tmp_path))
    report = result.report()
    assert "state" not in report and report["changed_paths"] == [pam_run.STATE_PATH]
    assert report["receipt"]["feed_statuses"] == {"products": [200], "specs": [200]}
    assert "COPY-ME-NOT" not in json.dumps(report)
