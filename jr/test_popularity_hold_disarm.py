"""Every popularity HOLD leaves the pinned bot popularity PR disarmed, or says it could not.

A HOLD returns before publish() could disarm a refreshed PR, so an earlier hour's armed PR would
still auto-merge an edit the hold exists to stop. On each HOLD path run() looks the bot popularity
PR up again and, only when this runner pinned its exact head, runs publish._ensure_disarmed
(`gh pr merge <url> --disable-auto`, then a readback). Anything else is never modified. Fake gh,
git and state only; the exact gh argv sequence is asserted.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

import pending_prs
import popularity_delivery
import popularity_run
import publish
import tick
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)
URL = "https://github.com/o/r/pull/8"
BRANCH = "jr/popularity-20261107-0100"
HEAD, MOVED = "b" * 40, "d" * 40
ORPHAN = "jr/popularity-20261107-0200"
RECEIPT = "docs/telemetry/popularity/2026-11-07T02.json"

OPEN_INVENTORY = ("pr", "list", "--state", "open", "--limit", str(tick.OPEN_PR_LIMIT), "--json",
                  f"number,createdAt,headRefName,mergeable,labels,{pending_prs.PR_LIST_FIELDS}")
CLOSED_INVENTORY = ("pr", "list", "--state", "closed", "--limit", str(pending_prs.CLOSED_PR_LIMIT),
                    "--search", "is:unmerged closed:>=" +
                    (NOW - timedelta(days=pending_prs.VETO_TTL_DAYS)).date().isoformat(),
                    "--json", f"number,headRefName,closedAt,mergedAt,{pending_prs.PR_LIST_FIELDS}")
RECOVERY_SEARCH = ("pr", "list", "--state", "all", "--head", ORPHAN, "--limit", "100",
                   "--json", "url,state,headRefOid,author")
LOOKUP = ("pr", "list", "--state", "open", "--limit", "500", "--json",
          "number,url,headRefName,headRefOid,baseRefName,labels,author,isDraft")
VIEW = ("pr", "view", URL, "--json", "state,headRefOid,autoMergeRequest")
DISABLE = ("pr", "merge", URL, "--disable-auto")
READS = {("pr", "list"), ("pr", "view")}


def _tick_pr(number, fids):
    paths = [f"data/firmware/{fid}/firmware.md" for fid in fids]
    return {"number": number, "headRefName": "jr/tick-20261107-0100", "headRefOid": f"oid{number}",
            "author": {"login": publish.JR_LOGIN}, "isCrossRepository": False, "body": "",
            "files": [{"path": p} for p in paths], "changedFiles": len(paths)}


def _popularity_pr(login=publish.JR_LOGIN):
    return {"number": 8, "url": URL, "headRefName": BRANCH, "headRefOid": HEAD, "baseRefName": "main",
            "labels": [], "author": {"login": login}, "isDraft": False}


def _merge_state(head=HEAD, armed=True, state="OPEN"):
    return {"state": state, "headRefOid": head,
            "autoMergeRequest": {"enabledAt": "2026-11-07T01:00:00Z"} if armed else None}


class FakeGh:
    """Scripted gh. `popularity` is the open popularity-PR list (or a raw string / failing rc);
    `views` answers each successive `pr view`; `disable_rc` is the `--disable-auto` exit code."""

    def __init__(self, *, open_rc=0, popularity=(), lookup_rc=0, views=(), disable_rc=0):
        self.calls: list[tuple] = []
        self.open_rc, self.lookup_rc, self.disable_rc = open_rc, lookup_rc, disable_rc
        self.popularity, self.views = popularity, list(views)
        self.unexpected: list[tuple] = []

    def _answer(self, args, rc, value):
        stdout = value if isinstance(value, str) else json.dumps(value)
        return subprocess.CompletedProcess(args, rc, stdout, "" if rc == 0 else "HTTP 502")

    def __call__(self, *args):
        self.calls.append(args)
        if args == OPEN_INVENTORY:
            return self._answer(args, self.open_rc, [_tick_pr(1500, ["held"])])
        if args == CLOSED_INVENTORY or args == RECOVERY_SEARCH:
            return self._answer(args, 0, [])
        if args == LOOKUP:
            return self._answer(args, self.lookup_rc, self.popularity)
        if args == VIEW and self.views:
            return self._answer(args, 0, self.views.pop(0))
        if args == DISABLE:
            return self._answer(args, self.disable_rc, "")
        self.unexpected.append(args)
        raise AssertionError(f"unexpected gh call {args}")

    def mutating(self) -> list[tuple]:
        return [call for call in self.calls if call[:2] not in READS]


def _pin(state_file, **extra):
    popularity_run._write_state(state_file, {"published_head": {"url": URL, "branch": BRANCH, "sha": HEAD},
                                             **extra})


def _git(diff=None):
    def git(*args):
        if args[:2] == ("ls-remote", "origin"):
            return subprocess.CompletedProcess(args, 0, "c" * 40 + f"\trefs/heads/{ORPHAN}\n", "")
        if args[2:4] == ("diff", "--name-only"):
            return subprocess.CompletedProcess(args, 1 if diff is None else 0, "\n".join(diff or []), "")
        raise AssertionError(f"unexpected git call {args}")
    return git


@pytest.fixture
def effects(tmp_path, monkeypatch):
    """Protection, delivery and worktree are recorded effects; publication must never be reached."""
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    monkeypatch.setattr(publish, "protection_status", lambda *a, **k: publish.ProtectionStatus(True))
    monkeypatch.setattr(publish, "add_worktree", lambda **k: publish.Worktree(tmp_path, "a" * 40))
    monkeypatch.setattr(publish, "prepare_existing_popularity_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_delivery, "reconcile", lambda *a, **k: [])
    monkeypatch.setattr(publish, "publish",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a HOLD never publishes")))


def _hold(tmp_path, path, gh, *, dry_run=False, pinned=True):
    """Drive the real runner into HOLD `path`; return (result, the gh calls before the hold)."""
    state_file = tmp_path / "state.json"
    extra, git, prefix = {}, _git(), [OPEN_INVENTORY, CLOSED_INVENTORY]
    if path == "inventory":
        gh.open_rc, prefix = 1, [OPEN_INVENTORY]
    elif path == "recovery_deferred":
        extra = {"publication_intent": {
            "sha": "c" * 40, "branch": ORPHAN, "paths": ["data/firmware/held/firmware.md", RECEIPT],
            "samples": [], "receipt": RECEIPT, "subject": "s", "body": "b", "existing_pr_url": None,
            "expected_head_sha": None, "started_at": NOW.isoformat()}}
        prefix = prefix + [RECOVERY_SEARCH]
    elif path == "recovery_held":
        extra = {"publication_intent": {"sha": "not-a-sha"}}
    elif path in ("branch_held", "branch_unreadable"):
        git = _git(["data/firmware/held/firmware.md", RECEIPT] if path == "branch_held" else None)
        prefix = prefix + [LOOKUP]
    elif path == "unpinned":
        prefix = prefix + [LOOKUP]
    if pinned:
        _pin(state_file, **extra)
    else:
        popularity_run._write_state(state_file, {"published_head": {"url": URL, "branch": BRANCH,
                                                                    "sha": MOVED}, **extra})
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=state_file, dry_run=dry_run)
    assert not result["ok"] and result["stage"] is None and result["publish"] is None
    assert gh.unexpected == []
    return result, prefix


PINNED_PATHS = ["inventory", "recovery_deferred", "recovery_held", "branch_held", "branch_unreadable"]
HOLD_REASON = {"inventory": "pending-PR inventory incomplete", "recovery_deferred": "recovery deferred",
               "recovery_held": "publication recovery held", "branch_held": "open Jr tick PR holds",
               "branch_unreadable": "changes unreadable", "unpinned": "lacks matching local bot publication pin"}

# case -> (merge-state views, disable rc, expected tail after LOOKUP, disarm outcome)
PINNED_CASES = {
    "armed": ([_merge_state(), _merge_state(armed=False)], 0, [VIEW, DISABLE, VIEW], "verified"),
    "already_unarmed": ([_merge_state(armed=False)], 0, [VIEW], "verified"),
    "disable_fails": ([_merge_state()], 1, [VIEW, DISABLE], "failed: "),
    "readback_armed": ([_merge_state(), _merge_state()], 0, [VIEW, DISABLE, VIEW], "failed: "),
    "head_moved": ([_merge_state(head=MOVED)], 0, [VIEW], "failed: "),
    "closed": ([_merge_state(state="MERGED")], 0, [VIEW], "failed: "),
}
FAILURE_WORD = {"disable_fails": "disable-auto failed", "readback_armed": "still armed",
                "head_moved": "head moved", "closed": "not OPEN"}


def _assert_reported(result, outcome):
    assert result["disarm"].startswith(outcome)
    safe = outcome in ("none", "verified")
    assert result["hold_safe"] is safe
    assert f"disarm {result['disarm']}" in result["reason"]
    assert ("hold safe" if safe else "HOLD UNSAFE") in result["reason"]
    assert result["reason"] in popularity_run.render_line(result)


@pytest.mark.parametrize("case", list(PINNED_CASES))
@pytest.mark.parametrize("path", PINNED_PATHS)
def test_pinned_bot_popularity_pr_is_disarmed_on_every_hold(tmp_path, effects, path, case):
    views, disable_rc, tail, outcome = PINNED_CASES[case]
    gh = FakeGh(popularity=[_popularity_pr()], views=views, disable_rc=disable_rc)
    result, prefix = _hold(tmp_path, path, gh)
    assert HOLD_REASON[path] in result["reason"]
    assert gh.calls == prefix + [LOOKUP] + tail
    assert gh.mutating() == ([DISABLE] if DISABLE in tail else [])
    _assert_reported(result, outcome)
    if case in FAILURE_WORD:
        assert FAILURE_WORD[case] in result["disarm"]


@pytest.mark.parametrize("path", PINNED_PATHS[:3] + ["unpinned"])
def test_unpinned_bot_popularity_pr_is_never_modified(tmp_path, effects, path):
    gh = FakeGh(popularity=[_popularity_pr()], views=[_merge_state()])
    result, prefix = _hold(tmp_path, path, gh, pinned=False)
    assert HOLD_REASON[path] in result["reason"]
    assert gh.calls == prefix + [LOOKUP] and gh.mutating() == []
    _assert_reported(result, "unverified: not modified")


@pytest.mark.parametrize("path", PINNED_PATHS[:3])
def test_human_authored_popularity_pr_is_not_selected_and_never_modified(tmp_path, effects, path):
    gh = FakeGh(popularity=[_popularity_pr(login="a-human")], views=[_merge_state()])
    result, prefix = _hold(tmp_path, path, gh)   # even the local pin naming it changes nothing
    assert gh.calls == prefix + [LOOKUP] and gh.mutating() == []
    _assert_reported(result, "unverified: not modified")


@pytest.mark.parametrize("pr", [{"isDraft": True}, {"labels": [{"name": "jr-review"}]},
                                {"baseRefName": "dev"}, "two"], ids=["draft", "review", "base", "two"])
def test_non_auto_or_ambiguous_bot_popularity_pr_is_never_modified(tmp_path, effects, pr):
    prs = [_popularity_pr(), {**_popularity_pr(), "number": 9}] if pr == "two" else [{**_popularity_pr(), **pr}]
    gh = FakeGh(popularity=prs, views=[_merge_state()])
    result, prefix = _hold(tmp_path, "inventory", gh)
    assert gh.calls == prefix + [LOOKUP] and gh.mutating() == []
    _assert_reported(result, "unverified: not modified")


@pytest.mark.parametrize("path", PINNED_PATHS[:3])
def test_no_bot_popularity_pr_is_a_safe_hold(tmp_path, effects, path):
    gh = FakeGh(popularity=[])
    result, prefix = _hold(tmp_path, path, gh)
    assert gh.calls == prefix + [LOOKUP]
    _assert_reported(result, "none")


@pytest.mark.parametrize("lookup", [{"lookup_rc": 1}, {"popularity": "not json"}, {"popularity": {"a": 1}}],
                         ids=["unavailable", "unreadable", "malformed"])
@pytest.mark.parametrize("path", PINNED_PATHS[:3])
def test_unreadable_lookup_fails_the_disarm_without_raising(tmp_path, effects, path, lookup):
    gh = FakeGh(**lookup)
    result, prefix = _hold(tmp_path, path, gh)
    assert gh.calls == prefix + [LOOKUP] and gh.mutating() == []
    _assert_reported(result, "failed: ")
    assert HOLD_REASON[path] in result["reason"]


def test_dry_run_reports_would_disarm_and_never_mutates(tmp_path, effects):
    gh = FakeGh(popularity=[_popularity_pr()], views=[_merge_state()])
    result, prefix = _hold(tmp_path, "inventory", gh, dry_run=True)
    assert gh.calls == prefix + [LOOKUP] and gh.mutating() == []
    assert result["disarm"] == f"would-disarm {URL}" and result["hold_safe"] is False
    assert "HOLD UNSAFE" in result["reason"]


def test_pending_load_raising_is_an_unreadable_inventory_hold_that_disarms(tmp_path, effects, monkeypatch):
    monkeypatch.setattr(pending_prs, "load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    gh = FakeGh(popularity=[_popularity_pr()], views=[_merge_state(), _merge_state(armed=False)])
    _pin(tmp_path / "state.json")
    result = popularity_run.run(now=NOW, gh=gh, git=_git(), guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=tmp_path / "state.json")
    assert "pending-PR inventory" in result["reason"] and "boom" in result["reason"]
    assert gh.calls == [OPEN_INVENTORY, LOOKUP, VIEW, DISABLE, VIEW]   # load raised before its closed list
    _assert_reported(result, "verified")
