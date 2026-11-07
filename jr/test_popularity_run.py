"""The popularity PR is guarded and staged independently of growth changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import popularity_run
import publish
from test_popularity_full import _ctx
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)


def test_runner_publishes_only_popularity_paths_and_receipt(tmp_path, monkeypatch):
    path = _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    unrelated = tmp_path / "data/recipes/unreviewed/recipe.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("not part of popularity")
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: None)
    captured = {}

    def fake_publish(wt, paths, subject, body, **kwargs):
        captured.update(paths=paths, subject=subject, body=body, branch=kwargs["branch"])
        return publish.PublishResult(True, branch=kwargs["branch"],
                                     pr_url="https://github.com/o/r/pull/1", route="auto")

    monkeypatch.setattr(publish, "publish", fake_publish)
    ctx, _ = _ctx(tmp_path)
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=ctx.budget)
    assert result["ok"] and result["publish"]["route"] == "auto"
    assert captured["paths"] == ["data/firmware/fw/firmware.md",
                                 "docs/telemetry/popularity/2026-11-07T02.json"]
    assert str(unrelated.relative_to(tmp_path)) not in captured["paths"]
    assert captured["branch"].startswith("jr/popularity-")
    assert "proposed, not a deployed freshness claim" in captured["body"]
    assert "github_as_of" in path.read_text()


def test_guard_failure_keeps_everything_off_remote(tmp_path, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: None)
    monkeypatch.setattr(publish, "publish", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not publish")))
    ctx, _ = _ctx(tmp_path)
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": False, "output": "bad citation"},
                                repo_slug="o/r", budget=ctx.budget)
    assert not result["ok"] and result["reason"].startswith("guard red")
    assert result["publish"] is None


def test_pending_pr_is_reused_with_exact_head_lease(tmp_path, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    pending = {"url": "https://github.com/o/r/pull/8", "headRefName": "jr/popularity-20261107-0100",
               "headRefOid": "b" * 40}
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: pending)
    captured = {}

    def fake_publish(wt, paths, subject, body, **kwargs):
        captured.update(kwargs)
        return publish.PublishResult(True, branch=kwargs["branch"], pr_url=pending["url"], route="auto")

    monkeypatch.setattr(publish, "publish", fake_publish)
    ctx, _ = _ctx(tmp_path)
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=ctx.budget, state_file=tmp_path / "state.json")
    assert result["ok"] and result["pending_pr"] == pending["url"]
    assert captured["branch"] == pending["headRefName"]
    assert captured["existing_pr_url"] == pending["url"]
    assert captured["expected_head_sha"] == "b" * 40


def test_pending_pr_lookup_rejects_review_label_and_duplicates():
    from types import SimpleNamespace

    def gh_with(prs):
        return lambda *args: SimpleNamespace(returncode=0, stdout=json.dumps(prs))

    one = {"number": 8, "url": "https://github.com/o/r/pull/8",
           "headRefName": "jr/popularity-20261107-0100", "headRefOid": "b" * 40,
           "baseRefName": "main", "author": {"login": publish.JR_LOGIN}, "labels": []}
    assert popularity_run._pending_popularity_pr(gh_with([one])) == one
    labelled = {**one, "labels": [{"name": "jr-review"}]}
    import pytest
    with pytest.raises(RuntimeError, match="not an AUTO"):
        popularity_run._pending_popularity_pr(gh_with([labelled]))
    with pytest.raises(RuntimeError, match="2 pending"):
        popularity_run._pending_popularity_pr(gh_with([one, {**one, "number": 9}]))


def test_cooldown_state_survives_a_new_runner_process(tmp_path):
    path = tmp_path / "state.json"
    assert popularity_run._load_cooldown(path) is None
    popularity_run._save_cooldown(path, "2026-11-07T04:00:00+00:00")
    assert popularity_run._load_cooldown(path) == "2026-11-07T04:00:00+00:00"
    path.write_text("{damaged")
    assert popularity_run._load_cooldown(path) is None
