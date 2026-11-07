"""The popularity PR is guarded and staged independently of growth changes."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

import popularity_run
import publish
from budget import Budget
from test_popularity_full import _ctx
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("delivery_seconds,expected_attempts", [(40, 1), (70, 0)])
def test_slow_delivery_has_separate_source_and_overall_clocks(
        tmp_path, monkeypatch, delivery_seconds, expected_attempts):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: None)
    monkeypatch.setattr(publish, "publish", lambda *a, **k: publish.PublishResult(
        True, branch=k["branch"], pr_url="https://github.com/o/r/pull/1", route="auto"))

    class Clock:
        seconds = 0.0

        def __call__(self):
            return self.seconds

    clock = Clock()

    def slow_delivery(*args, **kwargs):
        clock.seconds += delivery_seconds
        return []

    monkeypatch.setattr(popularity_run.popularity_delivery, "reconcile", slow_delivery)
    ctx, _ = _ctx(tmp_path)
    source_calls = []

    def source_gh(*args):
        source_calls.append(args)
        clock.seconds += 1
        return ctx.gh(*args)

    budget = Budget(max_calls=12, max_seconds=60, clock=clock)
    result = popularity_run.run(now=NOW, gh=source_gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=budget,
                                state_file=tmp_path / "state.json", clock=clock)
    assert len(source_calls) == expected_attempts + (1 if expected_attempts else 0)
    if expected_attempts:
        assert result["coverage"]["attempted_repositories"] == 1
        assert result["complete_attempt"] and result["ok"]
        assert budget.elapsed() == len(source_calls)
    else:
        assert not result["ok"] and result["stage"] is None
        assert "eligible records deferred" in result["reason"]
        assert budget.calls == 0
        assert "source window not started" in result["graphql_budget"]
    assert result["overall_seconds"] == delivery_seconds + len(source_calls)


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
                                repo_slug="o/r", budget=ctx.budget,
                                state_file=tmp_path / "state.json")
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
                                repo_slug="o/r", budget=ctx.budget,
                                state_file=tmp_path / "state.json")
    assert not result["ok"] and result["reason"].startswith("guard red")
    assert result["publish"] is None


def test_pending_pr_is_reused_only_after_pinned_head_preparation(tmp_path, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    prepared = []
    monkeypatch.setattr(publish, "prepare_existing_popularity_worktree",
                        lambda wt, branch, head, **k: prepared.append((branch, head)))
    pending = {"url": "https://github.com/o/r/pull/8", "headRefName": "jr/popularity-20261107-0100",
               "headRefOid": "b" * 40}
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: pending)
    state_file = tmp_path / "state.json"
    popularity_run._write_state(state_file, {"published_head": {
        "url": pending["url"], "branch": pending["headRefName"], "sha": pending["headRefOid"]}})
    captured = {}

    def fake_publish(wt, paths, subject, body, **kwargs):
        captured.update(kwargs)
        kwargs["on_committed"]("c" * 40, kwargs["branch"], paths)
        kwargs["on_pr_ready"](pending["url"], "c" * 40, kwargs["branch"], paths)
        return publish.PublishResult(True, branch=kwargs["branch"], commit="c" * 40,
                                     pr_url=pending["url"], route="auto")

    monkeypatch.setattr(publish, "publish", fake_publish)
    ctx, _ = _ctx(tmp_path)
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=ctx.budget, state_file=state_file)
    assert result["ok"] and result["pending_pr"] == pending["url"]
    assert captured["branch"] == pending["headRefName"]
    assert captured["existing_pr_url"] == pending["url"]
    assert captured["expected_head_sha"] == "b" * 40
    assert prepared == [(pending["headRefName"], pending["headRefOid"])]
    assert popularity_run._load_state(state_file)["published_head"]["sha"] == "c" * 40


def test_existing_human_head_before_lookup_is_preserved(tmp_path, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    pending = {"url": "https://github.com/o/r/pull/8", "headRefName": "jr/popularity-20261107-0100",
               "headRefOid": "h" * 40}  # human commit already observed at lookup
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: pending)
    monkeypatch.setattr(publish, "publish", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not push")))
    state_file = tmp_path / "state.json"
    popularity_run._write_state(state_file, {"published_head": {
        "url": pending["url"], "branch": pending["headRefName"], "sha": "b" * 40}})
    ctx, _ = _ctx(tmp_path)
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=ctx.budget, state_file=state_file)
    assert not result["ok"] and "preserve branch" in result["reason"]


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
    assert not popularity_run._state_integrity(path)


def test_corrupt_persistent_state_refuses_new_publication(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{damaged")
    result = popularity_run.run(now=NOW, state_file=path)
    assert not result["ok"] and result["publish"] is None
    assert "preserve pending PR" in result["reason"]


def _intent(path, existing=None):
    popularity_run._save_publication_intent(path, sha="c" * 40,
        branch="jr/popularity-20261107-0200", paths=["data/firmware/fw/firmware.md"],
        samples=[{"id": "fw", "stars": 40, "forks": 5,
                  "github_as_of": "2026-11-07T02:00:00Z"}],
        receipt="docs/telemetry/popularity/2026-11-07T02.json",
        subject="hourly popularity", body="evidence", existing_pr_url=existing,
        expected_head_sha="b" * 40 if existing else None, now=NOW)


def test_intent_before_push_is_durably_cleared_only_after_remote_absence(tmp_path):
    path = tmp_path / "state.json"
    _intent(path)
    def gh(*args):
        assert args[:2] == ("pr", "list")
        return subprocess.CompletedProcess(args, 0, "[]", "")
    def git(*args):
        assert args[:2] == ("ls-remote", "origin")
        return subprocess.CompletedProcess(args, 0, "", "")
    assert popularity_run._recover_publication_intent(path, gh, git) == "discarded unpushed intent"
    assert "publication_intent" not in popularity_run._load_state(path)


def test_intent_after_push_before_pr_creates_unarmed_pr_and_registers_delivery(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    _intent(path)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (True, ""))
    calls = []
    def gh(*args):
        calls.append(args)
        if args[:2] == ("pr", "list"):
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[:2] == ("pr", "create"):
            return subprocess.CompletedProcess(args, 0, "https://github.com/o/r/pull/9\n", "")
        raise AssertionError(args)
    def git(*args):
        assert args[:2] == ("ls-remote", "origin")
        return subprocess.CompletedProcess(args, 0,
            "c" * 40 + "\trefs/heads/jr/popularity-20261107-0200\n", "")
    recovered = popularity_run._recover_publication_intent(path, gh, git)
    assert "pull/9" in recovered
    assert any("--draft" in call for call in calls if call[:2] == ("pr", "create"))
    assert not any(call[:2] == ("pr", "merge") for call in calls)
    state = popularity_run._load_state(path)
    assert "publication_intent" not in state
    assert state["published_head"]["sha"] == "c" * 40
    assert state["deliveries"][0]["state"] == "pending"


@pytest.mark.parametrize("pr_state", ["OPEN", "MERGED"])
def test_intent_after_pr_creation_recovers_exact_pr_across_restart(tmp_path, pr_state, monkeypatch):
    path = tmp_path / "state.json"
    _intent(path)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (True, ""))
    def gh(*args):
        assert args[:2] == ("pr", "list")
        return subprocess.CompletedProcess(args, 0, json.dumps([{
            "url": "https://github.com/o/r/pull/9", "state": pr_state,
            "headRefOid": "c" * 40, "author": {"login": publish.JR_LOGIN}}]), "")
    recovered = popularity_run._recover_publication_intent(path, gh,
        lambda *a: (_ for _ in ()).throw(AssertionError("no branch query needed")))
    assert "pull/9" in recovered
    state = popularity_run._load_state(path)
    assert "publication_intent" not in state
    assert state["deliveries"][0]["head_sha"] == "c" * 40


def test_existing_pr_intent_recovers_updated_head_but_refuses_human_head(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    url = "https://github.com/o/r/pull/8"
    _intent(path, existing=url)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (True, ""))
    def gh(head):
        return lambda *args: subprocess.CompletedProcess(args, 0, json.dumps({
            "url": url, "state": "OPEN", "headRefOid": head,
            "author": {"login": publish.JR_LOGIN}}), "")
    with pytest.raises(RuntimeError, match="head changed"):
        popularity_run._recover_publication_intent(path, gh("h" * 40), lambda *a: None)
    assert "publication_intent" in popularity_run._load_state(path)
    recovered = popularity_run._recover_publication_intent(path, gh("c" * 40), lambda *a: None)
    assert "pull/8" in recovered
    assert popularity_run._load_state(path)["published_head"]["sha"] == "c" * 40


def test_recovery_label_failure_keeps_intent_and_draft_pending_pr_is_not_auto(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    _intent(path)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (False, "denied"))
    def gh(*args):
        return subprocess.CompletedProcess(args, 0, json.dumps([{
            "url": "https://github.com/o/r/pull/9", "state": "OPEN",
            "headRefOid": "c" * 40, "author": {"login": publish.JR_LOGIN}}]), "")
    with pytest.raises(RuntimeError, match="needs jr-review label"):
        popularity_run._recover_publication_intent(path, gh, lambda *a: None)
    assert "publication_intent" in popularity_run._load_state(path)
    one = {"number": 9, "url": "https://github.com/o/r/pull/9",
           "headRefName": "jr/popularity-20261107-0200", "headRefOid": "c" * 40,
           "baseRefName": "main", "author": {"login": publish.JR_LOGIN},
           "labels": [], "isDraft": True}
    with pytest.raises(RuntimeError, match="not an AUTO"):
        popularity_run._pending_popularity_pr(lambda *a: subprocess.CompletedProcess(a, 0, json.dumps([one]), ""))


def test_nonzero_http200_graphql_rate_error_persists_runner_cooldown(tmp_path, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: None)
    monkeypatch.setattr(publish, "publish", lambda *a, **k: publish.PublishResult(
        True, branch=k["branch"], pr_url="https://github.com/o/r/pull/1", route="auto"))

    def rate_error(doc, call_number):
        return {"errors": [{"type": "RATE_LIMITED", "message": "rate limit exceeded"}]} if call_number == 2 else doc

    ctx, calls = _ctx(tmp_path, doc_transform=rate_error, nonzero_calls=(2,))
    state = tmp_path / "cooldown.json"
    result = popularity_run.run(now=NOW, gh=ctx.gh, guard=lambda root: {"ok": True},
                                repo_slug="o/r", budget=ctx.budget, state_file=state)
    assert len(calls) == 2
    assert result["cooldown_until"] == popularity_run._load_cooldown(state)
    assert result["cooldown_until"] >= "2026-11-07T03:00:00"
    assert result["coverage"]["attempted_repositories"] == 1


@pytest.mark.parametrize("status,as_bytes", [(403, True), (429, False)])
def test_timed_out_rate_headers_persist_cooldown_and_suppress_next_run(tmp_path, monkeypatch, status, as_bytes):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: None)
    monkeypatch.setattr(publish, "publish", lambda *a, **k: publish.PublishResult(
        True, branch=k["branch"], pr_url="https://github.com/o/r/pull/1", route="auto"))
    calls = []
    def fake_subprocess(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return subprocess.CompletedProcess(argv, 0,
                'HTTP/2.0 200 OK\n\n{"data":{"rateLimit":{"cost":1,"remaining":4999}}}', '')
        if len(calls) == 2:
            captured = f"HTTP/2.0 {status} ERROR\nRetry-After: 7200\n\n{{truncated"
            raise subprocess.TimeoutExpired(argv, 8, output=captured.encode() if as_bytes else captured,
                                            stderr=b"" if as_bytes else "")
        raise AssertionError("cooldown must suppress the next source request")
    monkeypatch.setattr(subprocess, "run", fake_subprocess)
    state = tmp_path / "cooldown.json"
    first = popularity_run.run(now=NOW, gh=publish.default_gh, guard=lambda root: {"ok": True},
                               repo_slug="o/r", state_file=state)
    assert len(calls) == 2 and first["coverage"]["attempted_repositories"] == 1
    assert first["cooldown_until"] >= (NOW + timedelta(hours=2)).isoformat()
    second = popularity_run.run(now=NOW + timedelta(hours=1), gh=publish.default_gh,
                                guard=lambda root: {"ok": True}, repo_slug="o/r", state_file=state)
    assert len(calls) == 2 and second["coverage"]["attempted_repositories"] == 0
