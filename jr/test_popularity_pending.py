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
    assert not {"graphql", "protection", "worktree", "delivery", "publish", "popularity_pr_lookup"} & set(events)
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
    assert result["coverage"] == {"eligible_repositories": 2, "attempted_repositories": 2,
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

