"""The hourly popularity pass never edits a firmware an OPEN Jr tick PR already changes (R3).

popularity_run.run reads the same pending-PR index the growth tick does (jr/pending_prs.py) BEFORE
any source read, worktree or publication, and fails closed when that inventory may miss a hold.
popularity_full defers every open-held record: never queried, never rewritten, disclosed in the
receipt, and the attempt is not complete while one is deferred. Fake gh, git and state only.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import pytest

import pending_prs
import popularity_delivery
import popularity_full
import popularity_run
import publish
import tick
from test_popularity_full import ALIAS, _ctx
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)
RECEIPT = "docs/telemetry/popularity/2026-11-07T02.json"
REAL_RUNNER = popularity_run.run   # bound before a test patches the module attribute


def _tick_pr(number, fids, *, changed=None, closed_at=None):
    """A Jr bot tick PR from this repository, as the preflight's `gh pr list --json files…` lists it."""
    paths = [f"data/firmware/{fid}/firmware.md" for fid in fids]
    pr = {"number": number, "headRefName": "jr/tick-20261107-0100", "headRefOid": f"oid{number}",
          "author": {"login": publish.JR_LOGIN}, "isCrossRepository": False, "body": "",
          "files": [{"path": p} for p in paths], "changedFiles": len(paths) if changed is None else changed}
    if closed_at:
        pr.update(closedAt=closed_at, mergedAt=None)
    return pr


class FakeGh:
    """Scripted gh: the open/closed PR inventory, an unavailable REST file listing, and the GraphQL
    source (test_popularity_full._ctx). Every call is logged in `events` with its kind."""

    def __init__(self, root, events, *, open_prs=(), closed_prs=(), open_rc=0, closed_rc=0):
        self.source, self.queries = _ctx(root)
        self.events, self.calls = events, []
        self.open_prs, self.closed_prs = list(open_prs), list(closed_prs)
        self.open_rc, self.closed_rc = open_rc, closed_rc

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("api", "graphql"):
            self.events.append("graphql")
            return self.source.gh(*args)
        if args[:2] == ("pr", "list"):
            state, fields = args[args.index("--state") + 1], args[args.index("--json") + 1]
            if state == "open" and "files" in fields:
                self.events.append("open_inventory")
                return subprocess.CompletedProcess(args, self.open_rc, json.dumps(self.open_prs), "")
            if state == "closed":
                self.events.append("closed_inventory")
                return subprocess.CompletedProcess(args, self.closed_rc, json.dumps(self.closed_prs), "")
            self.events.append("popularity_pr_lookup")
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[:2] == ("pr", "create"):
            self.events.append("pr_create")
            return subprocess.CompletedProcess(args, 0, "https://github.com/o/r/pull/9\n", "")
        if args[:3] == ("pr", "view", "https://github.com/o/r/pull/9"):
            self.events.append("pr_readback")
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "url": args[2], "state": "OPEN", "headRefOid": "c" * 40,
                "author": {"login": publish.JR_LOGIN}, "autoMergeRequest": None}), "")
        if args[0] == "api" and "/pulls/" in args[1]:
            self.events.append("rest_files")
            return subprocess.CompletedProcess(args, 1, "", "HTTP 502")
        raise AssertionError(f"unexpected gh call {args}")

    def source_repos(self) -> list[list[str]]:
        """The repositories each GraphQL source query asked for (the quota probe asks for none)."""
        return [[f"{owner}/{name}" for _, owner, name in ALIAS.findall(q)] for q in self.queries]


@pytest.fixture
def effects(tmp_path, monkeypatch):
    """Worktree, protection, delivery and publication as recorded effects; `published` holds the
    paths every publish() call was asked to stage."""
    events: list[str] = []
    published: list[list[str]] = []

    def record(name, value=None):
        def effect(*a, **k):
            events.append(name)
            return value() if callable(value) else value
        return effect

    monkeypatch.setattr(publish, "protection_status", record("protection", lambda: publish.ProtectionStatus(True)))
    monkeypatch.setattr(publish, "add_worktree", record("worktree", lambda: publish.Worktree(tmp_path, "a" * 40)))
    monkeypatch.setattr(publish, "is_clean", lambda *a, **k: True)
    monkeypatch.setattr(publish, "remove_worktree", lambda *a, **k: None)
    monkeypatch.setattr(publish, "cleanup_branch", lambda *a, **k: None)
    monkeypatch.setattr(popularity_delivery, "reconcile", record("delivery", list))

    def fake_publish(wt, paths, subject, body, **kwargs):
        events.append("publish")
        published.append(list(paths))
        return publish.PublishResult(True, branch=kwargs["branch"], pr_url="https://github.com/o/r/pull/1",
                                     route="auto")

    monkeypatch.setattr(publish, "publish", fake_publish)
    return events, published


def _run(tmp_path, gh, **kw):
    return popularity_run.run(now=NOW, gh=gh, git=_no_git, guard=lambda root: {"ok": True},
                              repo_slug="o/r", state_file=tmp_path / "state.json", **kw)


def _no_git(*args):
    raise AssertionError(f"unexpected git call {args}")


def _receipt(root: Path) -> dict:
    return json.loads((root / RECEIPT).read_text())


def _row(receipt: dict, fid: str) -> dict:
    return next(row for row in receipt["records"] if row["firmware_id"] == fid)


# --- the three SEO probes ----------------------------------------------------------------------

def test_open_held_only_repository_gets_zero_graphql_calls(tmp_path, effects):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    events, published = effects
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = _run(tmp_path, gh)
    assert gh.queries == []                      # no quota probe, no repository query
    assert "graphql" not in events
    assert held.read_bytes() == before
    assert published == [[RECEIPT]]              # the receipt only, never the held record
    row = _row(_receipt(tmp_path), "held")
    assert row["outcome"] == "deferred_open_tick_pr" and row["attempted"] is False
    assert result["complete_attempt"] is False and result["ok"] is False


def test_shared_repository_queries_unheld_record_and_leaves_held_bytes_unchanged(tmp_path, effects):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    free = _record(tmp_path, "free", "owner/repo-001", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    events, published = effects
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = _run(tmp_path, gh)
    assert gh.source_repos() == [[], ["owner/repo-001"]]   # one probe, the shared repository once
    assert held.read_bytes() == before
    assert "github_repo_id: 1001" in free.read_text()
    assert published == [["data/firmware/free/firmware.md", RECEIPT]]
    receipt = _receipt(tmp_path)
    assert _row(receipt, "held")["outcome"] == "deferred_open_tick_pr"
    assert _row(receipt, "held")["attempted"] is False
    assert _row(receipt, "free")["outcome"] == "validated_update"
    assert receipt["deferred_open_tick_pr"] == 1
    assert receipt["state"] == "proposed_not_deployed"
    assert receipt["eligible_repositories"] == receipt["attempted_repositories"] == 1
    assert result["coverage"]["deferred_open_tick_pr"] == 1
    assert result["complete_attempt"] is False      # queried once, yet a record was deferred
    assert result["ok"] is False


def test_run_loads_pending_index_before_any_source_or_publication_step(tmp_path, effects, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    events, _ = effects
    loaded, seen = [], []
    real_load = pending_prs.load

    def spy_load(gh, open_prs, now, *, slug, open_limit):
        events.append("pending_prs.load")
        index = real_load(gh, open_prs, now, slug=slug, open_limit=open_limit)
        loaded.append((index, open_prs, slug, open_limit))
        return index

    real_stage = popularity_full.run

    def spy_stage(ctx):
        events.append("popularity_full.run")
        seen.append(ctx.pending)
        return real_stage(ctx)

    monkeypatch.setattr(pending_prs, "load", spy_load)
    monkeypatch.setattr(popularity_full, "run", spy_stage)
    tick_pr = _tick_pr(1500, ["other"])
    gh = FakeGh(tmp_path, events, open_prs=[tick_pr])
    result = _run(tmp_path, gh)
    assert result["ok"], result["reason"]
    first_effect = min(events.index(e) for e in
                       ("graphql", "protection", "worktree", "delivery", "publish", "popularity_pr_lookup",
                        "popularity_full.run"))
    assert events.index("open_inventory") < events.index("pending_prs.load") < first_effect
    index, open_prs, slug, limit = loaded[0]
    assert open_prs == [tick_pr] and slug == "o/r" and limit == tick.OPEN_PR_LIMIT
    assert index.complete and index.hold("other").state == pending_prs.OPEN
    assert seen == [index]                        # the very index reaches the stage on ctx


# --- fail closed --------------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["open_list_fails", "closed_list_fails", "open_list_cut",
                                  "file_list_incomplete"])
def test_incomplete_pending_inventory_fails_closed_before_any_source_or_publication(
        tmp_path, effects, case):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    state_file = tmp_path / "state.json"
    popularity_run._save_publication_intent(
        state_file, sha="c" * 40, branch="jr/popularity-20261107-0100", paths=[], samples=[],
        receipt=RECEIPT, subject="s", body="b", existing_pr_url=None, expected_head_sha=None, now=NOW)
    events, published = effects
    open_prs = {"open_list_cut": [_tick_pr(n, []) for n in range(tick.OPEN_PR_LIMIT)],
                "file_list_incomplete": [_tick_pr(1500, ["held"], changed=2)]}.get(case, [])
    gh = FakeGh(tmp_path, events, open_prs=open_prs, open_rc=1 if case == "open_list_fails" else 0,
                closed_rc=1 if case == "closed_list_fails" else 0)
    result = popularity_run.run(now=NOW, gh=gh, git=_no_git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=state_file)
    assert not result["ok"] and result["stage"] is None and result["publish"] is None
    assert "pending-PR inventory" in result["reason"]
    assert gh.queries == [] and published == []
    assert not {"graphql", "protection", "worktree", "delivery", "publish"} & set(events)
    # the HOLD's only later step is the read-only disarm lookup: no bot popularity PR, a safe hold
    assert events[-1] == "popularity_pr_lookup" and events.count("popularity_pr_lookup") == 1
    assert result["disarm"] == "none" and result["hold_safe"] is True
    assert not any(call[:2] == ("pr", "create") for call in gh.calls)
    assert popularity_run._load_state(state_file).get("publication_intent")   # recovery never ran
    assert held.read_bytes() == before
    assert not (tmp_path / RECEIPT).exists()


# --- end to end ----------------------------------------------------------------------------------

def test_held_only_repo_and_unheld_control_query_only_the_control(tmp_path, effects):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    control = _record(tmp_path, "control", "owner/repo-002", {"stars": 30, "forks": 3})
    vetoed = _record(tmp_path, "vetoed", "owner/repo-003", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    events, published = effects
    veto = _tick_pr(1400, ["vetoed"], closed_at="2026-11-06T00:00:00Z")
    veto["files"] += [{"path": "data/recipes/m5cardputer__vetoed/recipe.md"}]
    veto["changedFiles"] = 2
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])], closed_prs=[veto])
    result = _run(tmp_path, gh)
    # A veto is no edit hold for a catalogued record's counts (stage_popularity_refresh semantics).
    assert gh.source_repos() == [[], ["owner/repo-002", "owner/repo-003"]]
    assert held.read_bytes() == before
    assert "github_repo_id: 1002" in control.read_text() and "github_repo_id: 1003" in vetoed.read_text()
    assert published == [["data/firmware/control/firmware.md", "data/firmware/vetoed/firmware.md", RECEIPT]]
    assert all("held" not in path for path in published[0])
    receipt = _receipt(tmp_path)
    assert receipt["deferred_open_tick_pr"] == 1
    assert receipt["outcomes"] == {"deferred_open_tick_pr": 1, "validated_update": 2}
    # the held repository stays in the denominator though never queried
    assert result["coverage"] == {"eligible_repositories": 3, "attempted_repositories": 2,
                                  "validated_repositories": 2, "deferred_open_tick_pr": 1}
    assert result["complete_attempt"] is False


def test_unheld_catalog_still_completes(tmp_path, effects):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    events, published = effects
    gh = FakeGh(tmp_path, events)
    result = _run(tmp_path, gh)
    assert result["ok"] and result["complete_attempt"] is True
    assert result["coverage"]["deferred_open_tick_pr"] == 0
    assert _receipt(tmp_path)["deferred_open_tick_pr"] == 0


def test_guarded_non_dry_tick_main_makes_no_real_gh_call_and_touches_no_live_state(
        tmp_path, effects, monkeypatch):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    events, published = effects
    violations, state_paths = [], []
    for name in ("run", "Popen"):
        guarded = getattr(subprocess, name)   # conftest's guard: a real gh raises

        def spy(argv, *a, _guarded=guarded, **k):
            if isinstance(argv, (list, tuple)) and argv and Path(str(argv[0])).name == "gh":
                violations.append(argv)
            return _guarded(argv, *a, **k)

        monkeypatch.setattr(subprocess, name, spy)
    for name in ("_state_integrity", "_load_state", "_write_state"):
        guarded = getattr(popularity_run, name)

        def spy_state(path, *a, _guarded=guarded, **k):
            state_paths.append(Path(path))
            return _guarded(path, *a, **k)

        monkeypatch.setattr(popularity_run, name, spy_state)
    monkeypatch.setattr(popularity_run, "run",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("live popularity runner")))
    growth = []
    monkeypatch.setattr(tick, "run_tick", lambda **kw: growth.append(kw) or tick.report.TickReport(when=NOW))
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    runner = partial(REAL_RUNNER, gh=gh, git=_no_git, guard=lambda root: {"ok": True},
                     repo_slug="o/r", now=NOW, state_file=tmp_path / "state.json")
    assert tick.main(["--no-telegram"], popularity_runner=runner) == 1   # a deferred record: incomplete
    assert violations == []
    assert state_paths and all(p.is_relative_to(tmp_path) for p in state_paths)
    assert growth and growth[0]["dry_run"] is False
    assert gh.source_repos() == [[], ["owner/repo-002"]]
    assert published == [["data/firmware/free/firmware.md", RECEIPT]]
    assert held.read_bytes() == before



# --- checker follow-ups ---------------------------------------------------------------------------

POPULARITY_PR = {"number": 8, "url": "https://github.com/o/r/pull/8", "headRefName": "jr/popularity-20261107-0100",
                 "headRefOid": "b" * 40}


def _reuse_popularity_pr(tmp_path, monkeypatch, diff):
    """An earlier hour's bot popularity PR is reused at its pinned head; `diff` is what its prepared
    branch changes against main (`git diff --name-only`), or None when git cannot tell."""
    monkeypatch.setattr(popularity_run, "_pending_popularity_pr", lambda gh: POPULARITY_PR)
    monkeypatch.setattr(publish, "prepare_existing_popularity_worktree", lambda *a, **k: None)
    popularity_run._write_state(tmp_path / "state.json", {"published_head": {
        "url": POPULARITY_PR["url"], "branch": POPULARITY_PR["headRefName"], "sha": POPULARITY_PR["headRefOid"]}})
    seen = []

    def git(*args):
        seen.append(args)
        assert args == ("-C", str(tmp_path), "diff", "--name-only", "a" * 40, "HEAD"), args
        return subprocess.CompletedProcess(args, 1 if diff is None else 0, "\n".join(diff or []), "")
    return git, seen


@pytest.mark.parametrize("diff", [["data/firmware/held/firmware.md", RECEIPT], None])
def test_reused_popularity_pr_already_changing_a_held_record_is_preserved_unpublished(
        tmp_path, effects, monkeypatch, diff):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    events, published = effects
    git, seen = _reuse_popularity_pr(tmp_path, monkeypatch, diff)
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=tmp_path / "state.json")
    assert seen and not result["ok"] and result["publish"] is None and published == []
    assert gh.queries == [] and result["stage"] is None
    assert "preserve branch for review" in result["reason"]
    if diff:
        assert "held" in result["reason"] and "#1500" in result["reason"]


def test_reused_popularity_pr_not_touching_a_held_record_is_still_updated(tmp_path, effects, monkeypatch):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    events, published = effects
    git, _ = _reuse_popularity_pr(tmp_path, monkeypatch, ["data/firmware/free/firmware.md", RECEIPT])
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=tmp_path / "state.json")
    assert published == [["data/firmware/free/firmware.md", RECEIPT]]
    assert result["complete_attempt"] is False
    assert "1 deferred to an open Jr tick PR" in result["reason"]


@pytest.mark.parametrize("case,gap", [("open_list_fails", "unreadable"), ("closed_list_fails", "unreadable"),
                                      ("open_list_cut", "hit its limit"),
                                      ("file_list_incomplete", "cannot be listed whole")])
def test_fail_closed_reason_names_the_real_gap(tmp_path, effects, case, gap):
    events, _ = effects
    open_prs = {"open_list_cut": [_tick_pr(n, []) for n in range(tick.OPEN_PR_LIMIT)],
                "file_list_incomplete": [_tick_pr(1500, ["held"], changed=2)]}.get(case, [])
    gh = FakeGh(tmp_path, events, open_prs=open_prs, open_rc=1 if case == "open_list_fails" else 0,
                closed_rc=1 if case == "closed_list_fails" else 0)
    result = _run(tmp_path, gh)
    assert gap in result["reason"]


def test_pending_load_raising_fails_closed_before_any_effect(tmp_path, effects, monkeypatch):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    events, published = effects
    monkeypatch.setattr(pending_prs, "load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    gh = FakeGh(tmp_path, events)
    result = _run(tmp_path, gh)
    assert not result["ok"] and result["stage"] is None and "boom" in result["reason"]
    assert gh.queries == [] and published == []
    assert not {"protection", "worktree", "delivery", "publish"} & set(events)
    assert events == ["open_inventory", "popularity_pr_lookup"] and result["disarm"] == "none"   # read-only disarm lookup


def test_incomplete_for_another_reason_does_not_blame_a_tick_pr(tmp_path, effects):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    events, _ = effects
    gh = FakeGh(tmp_path, events)
    gh.source, gh.queries = _ctx(tmp_path, remaining=40)      # quota too low: nothing attempted
    result = _run(tmp_path, gh)
    assert result["complete_attempt"] is False
    assert "incomplete repository attempt coverage" in result["reason"]
    assert "deferred to an open Jr tick PR" not in result["reason"]


def _index(*held):
    return pending_prs.build([_tick_pr(1500, list(held))], [], NOW)


def test_dry_run_defers_held_record_without_a_would_write(tmp_path):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, dry_run=True)
    ctx.pending = _index("held")
    result = popularity_full.run(ctx)
    assert [w["path"] for w in result.would_write if w["field"] == "popularity"] == ["data/firmware/free/firmware.md"]
    receipt = next(w["value"] for w in result.would_write if w["field"] == "*")
    assert receipt["deferred_open_tick_pr"] == 1
    assert [[f"{o}/{n}" for _, o, n in ALIAS.findall(q)] for q in calls] == [[], ["owner/repo-002"]]


@pytest.mark.parametrize("kwargs", [{"cooldown_until": "2026-11-07T05:00:00+00:00"}, {"max_calls": 0}])
def test_early_return_keeps_held_records_deferred(tmp_path, kwargs):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, **kwargs)
    ctx.pending = _index("held")
    popularity_full.run(ctx)
    receipt = json.loads((tmp_path / RECEIPT).read_text())
    assert calls == [] and _row(receipt, "held")["outcome"] == "deferred_open_tick_pr"
    assert _row(receipt, "free")["outcome"].startswith("unattempted_")


# --- reviewer follow-ups: recovery honours OPEN holds; held repositories stay eligible ------------

ORPHAN = "jr/popularity-20261107-0100"
EARLIER_PIN = {"url": "https://github.com/o/r/pull/7", "branch": "jr/popularity-20261106-2300", "sha": "e" * 40}


def _orphan_intent(tmp_path, paths):
    """A pushed fresh popularity branch whose PR was never created (the process stopped after push)."""
    state_file = tmp_path / "state.json"
    popularity_run._write_state(state_file, {"published_head": dict(EARLIER_PIN)})
    popularity_run._save_publication_intent(
        state_file, sha="c" * 40, branch=ORPHAN, paths=paths, samples=[], receipt=RECEIPT,
        subject="s", body="b", existing_pr_url=None, expected_head_sha=None, now=NOW)
    return state_file


def _orphan_git(diff):
    """The remote holds the exact intent commit; `diff` is what that branch changes against main,
    or None when git cannot tell."""
    seen = []

    def git(*args):
        seen.append(args)
        if args[:2] == ("ls-remote", "origin"):
            return subprocess.CompletedProcess(args, 0, "c" * 40 + f"\trefs/heads/{ORPHAN}\n", "")
        if args[:2] == ("fetch", "origin"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ("rev-parse", "--verify"):
            return subprocess.CompletedProcess(args, 0, "c" * 40 + "\n", "")
        if args[:2] == ("diff", "--name-only"):
            return subprocess.CompletedProcess(args, 1 if diff is None else 0, "\n".join(diff or []), "")
        raise AssertionError(f"unexpected git call {args}")
    return git, seen


@pytest.mark.parametrize("intent_paths,diff", [
    (["data/firmware/held/firmware.md", RECEIPT], ["data/firmware/free/firmware.md", RECEIPT]),
    (["data/firmware/free/firmware.md", RECEIPT], ["data/firmware/held/firmware.md", RECEIPT]),
    (["data/firmware/free/firmware.md", RECEIPT], None),
], ids=["intent_paths_held", "branch_diff_held", "branch_diff_unreadable"])
def test_runner_defers_orphan_recovery_touching_an_open_held_record(
        tmp_path, effects, monkeypatch, intent_paths, diff):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    state_file = _orphan_intent(tmp_path, intent_paths)
    intent = popularity_run._load_state(state_file)["publication_intent"]
    monkeypatch.setattr(publish, "apply_review_label",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no label on a deferred recovery")))
    events, published = effects
    git, seen = _orphan_git(diff)
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=state_file)
    assert not any(call[:2] == ("pr", "create") for call in gh.calls) and "pr_create" not in events
    state = popularity_run._load_state(state_file)
    assert state["publication_intent"] == intent                    # kept for review
    assert state["published_head"] == EARLIER_PIN                  # unchanged
    assert "deliveries" not in state
    assert not any(args[0] in ("push", "branch", "update-ref") or "--delete" in args for args in seen)
    assert not result["ok"] and result["stage"] is None and result["publish"] is None
    assert gh.queries == [] and published == []
    assert not {"delivery", "protection", "worktree", "publish"} & set(events)
    assert "recovery deferred" in result["reason"] and ORPHAN in result["reason"]
    if diff is not None:
        assert "#1500: held" in result["reason"]
    if "data/firmware/held/firmware.md" in intent_paths:
        assert not any(args[0] == "fetch" for args in seen)     # held by its own intent: no git needed
    assert "deferred" in result["recovery"]


def test_runner_recovers_orphan_branch_not_touching_a_held_record(tmp_path, effects, monkeypatch):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    paths = ["data/firmware/free/firmware.md", RECEIPT]
    state_file = _orphan_intent(tmp_path, paths)
    monkeypatch.setattr(publish, "apply_review_label", lambda *a, **k: (True, ""))
    events, published = effects
    git, _ = _orphan_git(paths)
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = popularity_run.run(now=NOW, gh=gh, git=git, guard=lambda root: {"ok": True},
                                repo_slug="o/r", state_file=state_file)
    creates = [call for call in gh.calls if call[:2] == ("pr", "create")]
    assert len(creates) == 1 and "--draft" in creates[0] and ORPHAN in creates[0]
    state = popularity_run._load_state(state_file)
    assert "publication_intent" not in state
    assert state["published_head"] == {"url": "https://github.com/o/r/pull/9", "branch": ORPHAN, "sha": "c" * 40}
    assert "recovered exact popularity PR https://github.com/o/r/pull/9" in result["recovery"]
    assert published == [["data/firmware/free/firmware.md", RECEIPT]]   # the pass then runs as before


def test_held_only_repository_stays_in_the_eligible_denominator(tmp_path, effects):
    _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    events, _ = effects
    result = _run(tmp_path, FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])]))
    assert result["coverage"] == {"eligible_repositories": 1, "attempted_repositories": 0,
                                  "validated_repositories": 0, "deferred_open_tick_pr": 1}
    receipt = _receipt(tmp_path)
    assert (receipt["eligible_repositories"], receipt["attempted_repositories"]) == (1, 0)
    assert result["complete_attempt"] is False


def test_held_repository_plus_distinct_unheld_repository_is_eligible_two_attempted_one(tmp_path, effects):
    held = _record(tmp_path, "held", "owner/repo-001", {"stars": 30, "forks": 3})
    _record(tmp_path, "free", "owner/repo-002", {"stars": 30, "forks": 3})
    before = held.read_bytes()
    events, published = effects
    gh = FakeGh(tmp_path, events, open_prs=[_tick_pr(1500, ["held"])])
    result = _run(tmp_path, gh)
    assert gh.source_repos() == [[], ["owner/repo-002"]]          # still never queried
    assert held.read_bytes() == before                            # still never written
    assert published == [["data/firmware/free/firmware.md", RECEIPT]]
    assert result["coverage"] == {"eligible_repositories": 2, "attempted_repositories": 1,
                                  "validated_repositories": 1, "deferred_open_tick_pr": 1}
    receipt = _receipt(tmp_path)
    assert (receipt["eligible_repositories"], receipt["attempted_repositories"]) == (2, 1)
    assert result["complete_attempt"] is False and result["ok"] is False
