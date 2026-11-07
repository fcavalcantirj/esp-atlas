"""Orphan-branch recovery pins only the commit it verified, even when the branch moves (R3a).

The saved publication intent and `ls-remote` see the orphan branch at A. If the branch moves to B
before the recovery fetch, the hold diff must not vouch for A while `gh pr create` opens B; if it
moves after the fetch, the created PR must not be pinned at A. Driven through the real
popularity_run.run with temporary local git repositories behind a file:// remote and a recorded
fake gh: no network, no live state.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import popularity_delivery
import popularity_run
import publish
from test_popularity_pending import FakeGh, _tick_pr
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)
ORPHAN = "jr/popularity-20261107-0100"
RECEIPT = "docs/telemetry/popularity/2026-11-07T02.json"
FREE, HELD = "data/firmware/free/firmware.md", "data/firmware/held/firmware.md"
EARLIER_PIN = {"url": "https://github.com/o/r/pull/7", "branch": "jr/popularity-20261106-2300", "sha": "e" * 40}
CREATED = "https://github.com/o/r/pull/9"
IDENTITY = ("-c", "user.name=jr-test", "-c", "user.email=jr-test@example.invalid",
            "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(clone: Path, path: str, text: str) -> str:
    target = clone / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _git(clone, "add", path)
    _git(clone, "commit", "-q", "-m", f"edit {path}")
    return _git(clone, "rev-parse", "HEAD")


class Remote:
    """A bare file:// origin, the runner's clone holding the intent commit A, and a second clone
    that can move the orphan branch behind the runner's back."""

    def __init__(self, tmp_path: Path):
        self.bare, self.other, self.runner = tmp_path / "origin.git", tmp_path / "other", tmp_path / "runner"
        _git(tmp_path, "init", "-q", "--bare", str(self.bare))
        self.url = self.bare.as_uri()
        _git(tmp_path, "clone", "-q", self.url, str(self.other))
        _commit(self.other, "README.md", "base\n")
        _git(self.other, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(self.other, "checkout", "-q", "-b", ORPHAN)
        self.a = _commit(self.other, FREE, "unheld popularity edit\n")
        _git(self.other, "push", "-q", "origin", f"HEAD:refs/heads/{ORPHAN}")
        _git(tmp_path, "clone", "-q", self.url, str(self.runner))
        self.moved: str | None = None

    def move_branch(self) -> str:
        """Another writer adds an edit of the OPEN-held record to the orphan branch: A -> B."""
        self.moved = _commit(self.other, HELD, "edit of a record an open tick PR holds\n")
        _git(self.other, "push", "-q", "origin", f"HEAD:refs/heads/{ORPHAN}")
        return self.moved

    def head(self) -> str:
        return _git(self.runner, "ls-remote", self.url, f"refs/heads/{ORPHAN}").split()[0]

    def git(self, *, after: dict | None = None):
        """The runner's real git (cwd = its clone); `after[verb]` runs right after that git verb."""
        seen = []

        def git(*args):
            seen.append(args)
            done = subprocess.run(["git", *args], cwd=self.runner, capture_output=True, text=True)
            hook = (after or {}).get(args[0])
            if hook:
                hook()
            return done
        return git, seen


class RecordedGh(FakeGh):
    """FakeGh plus the recovery PR: `pr create` (optionally moving the branch), and `pr view`
    whose headRefOid is what the file:// remote really holds."""

    def __init__(self, root, events, remote: Remote, *, on_create=None, author=publish.JR_LOGIN,
                 armed=False, **kw):
        super().__init__(root, events, **kw)
        self.remote, self.on_create, self.author, self.armed = remote, on_create, author, armed

    def __call__(self, *args):
        if args[:2] == ("pr", "create"):
            self.calls.append(args)
            self.events.append("pr_create")
            if self.on_create:
                self.on_create()
            return subprocess.CompletedProcess(args, 0, CREATED + "\n", "")
        if args[:2] == ("pr", "view") and args[2] == CREATED:
            self.calls.append(args)
            view = {"url": CREATED, "state": "OPEN", "headRefOid": self.remote.head(),
                    "author": {"login": self.author},
                    "autoMergeRequest": {"enabledBy": {"login": "x"}} if self.armed else None}
            return subprocess.CompletedProcess(args, 0, json.dumps(view), "")
        if args[:3] == ("pr", "merge", CREATED) and "--disable-auto" in args:
            self.calls.append(args)
            self.armed = False
            return subprocess.CompletedProcess(args, 0, "", "")
        return super().__call__(*args)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A catalog with one OPEN-held and one free record, the orphan intent at A, and recorded effects."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    tree = tmp_path / "tree"
    _record(tree, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tree, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    remote = Remote(tmp_path)
    state_file = tmp_path / "state" / "state.json"
    popularity_run._write_state(state_file, {"published_head": dict(EARLIER_PIN)})
    popularity_run._save_publication_intent(
        state_file, sha=remote.a, branch=ORPHAN, paths=[FREE, RECEIPT], samples=[], receipt=RECEIPT,
        subject="s", body="b", existing_pr_url=None, expected_head_sha=None, now=NOW)
    events, published = [], []
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tree, "a" * 40))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (True, ""))
    monkeypatch.setattr(popularity_delivery, "reconcile", lambda *a, **k: [])

    def fake_publish(wt, paths, subject, body, **kwargs):
        published.append(list(paths))
        return publish.PublishResult(True, branch=kwargs["branch"], pr_url="https://github.com/o/r/pull/10",
                                     route="auto")

    monkeypatch.setattr(publish, "publish", fake_publish)
    return tree, remote, state_file, events, published


def _run(world, *, git_after=None, **gh_kw):
    tree, remote, state_file, events, _ = world
    intent = popularity_run._load_state(state_file)["publication_intent"]
    gh = RecordedGh(tree, events, remote, open_prs=[_tick_pr(1500, ["held"])], **gh_kw)
    git, seen = remote.git(after=git_after)
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=state_file)
    return result, gh, seen, intent


def _creates(gh) -> list[tuple]:
    return [call for call in gh.calls if call[:2] == ("pr", "create")]


def _assert_intent_kept(state_file, intent):
    state = popularity_run._load_state(state_file)
    assert state["publication_intent"] == intent
    assert state["published_head"] == EARLIER_PIN
    assert "deliveries" not in state


def _assert_branch_untouched(seen):
    assert not any(args[0] in ("push", "branch", "update-ref", "reset") or "--delete" in args
                   for args in seen)


def test_stable_head_control_recovers_and_pins_the_verified_commit(world):
    _, remote, state_file, _, published = world
    result, gh, seen, _ = _run(world)
    assert len(_creates(gh)) == 1 and "--draft" in _creates(gh)[0]
    assert any(args[0] == "fetch" for args in seen)            # an OPEN hold exists: the diff is real
    state = popularity_run._load_state(state_file)
    assert "publication_intent" not in state
    assert state["published_head"] == {"url": CREATED, "branch": ORPHAN, "sha": remote.a}
    assert result["recovery"] == f"recovered exact popularity PR {CREATED} at {remote.a}"
    assert published == [[FREE, RECEIPT]]


def test_branch_moved_before_fetch_defers_without_creating_a_pr(world):
    _, remote, state_file, _, published = world
    result, gh, seen, intent = _run(world, git_after={"ls-remote": remote.move_branch})
    assert remote.moved and remote.head() == remote.moved
    assert _creates(gh) == [] and published == []
    _assert_intent_kept(state_file, intent)
    _assert_branch_untouched(seen)
    assert remote.head() == remote.moved                       # the moved branch is left as found
    assert not result["ok"] and result["stage"] is None and result["publish"] is None
    assert "recovery deferred" in result["reason"] and ORPHAN in result["reason"]
    assert result["recovery"].startswith("deferred:")
    assert remote.moved in result["recovery"] and remote.a in result["recovery"]


@pytest.mark.parametrize("break_fetch", ["remote_gone", "fetch_head_missing"])
def test_unreadable_fetch_defers_without_creating_a_pr(world, break_fetch):
    tree, remote, state_file, _, published = world
    if break_fetch == "remote_gone":
        hooks = {"ls-remote": lambda: remote.bare.rename(remote.bare.with_name("gone.git"))}
    else:
        hooks = {"fetch": lambda: (remote.runner / ".git" / "FETCH_HEAD").unlink()}
    result, gh, seen, intent = _run(world, git_after=hooks)
    assert _creates(gh) == [] and published == []
    _assert_intent_kept(state_file, intent)
    _assert_branch_untouched(seen)
    assert "recovery deferred" in result["reason"] and ORPHAN in result["reason"]
    assert result["recovery"].startswith("deferred:")


@pytest.mark.parametrize("author,armed,disarm", [
    (publish.JR_LOGIN, False, "not armed"),
    (publish.JR_LOGIN, True, "verified"),
    ("felipe", True, "not modified"),
], ids=["jr_unarmed", "jr_armed_disarmed", "human_armed_untouched"])
def test_head_moved_after_pr_create_is_not_pinned_and_keeps_intent(world, author, armed, disarm):
    _, remote, state_file, _, published = world
    result, gh, seen, intent = _run(world, on_create=remote.move_branch, author=author, armed=armed)
    assert len(_creates(gh)) == 1                               # the fetch saw A; the PR got B
    _assert_intent_kept(state_file, intent)
    _assert_branch_untouched(seen)
    assert published == [] and result["publish"] is None and not result["ok"]
    assert result["recovery"].startswith("deferred:")
    assert CREATED in result["recovery"] and remote.moved in result["recovery"] and remote.a in result["recovery"]
    assert "not pinned" in result["recovery"] and f"disarm {disarm}" in result["recovery"]
    merges = [call for call in gh.calls if call[:2] == ("pr", "merge")]
    if disarm == "verified":
        assert merges == [("pr", "merge", CREATED, "--disable-auto")] and gh.armed is False
    else:
        assert merges == []
        assert gh.armed is armed                                # a human PR is never modified
