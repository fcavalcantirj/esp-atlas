"""Tests for jr/tick.py — the hourly tick skeleton, run entirely on recorders.

No test here runs git, gh, validate.py, pytest, Telegram or the network: git/gh are scripted
recorders, the gauge/guard/notifier/pr_state/revalidate are injected fakes, and the "worktree"
is a tmp_path. The real data/ tree is read by exactly one test (the dry-run gauge).

Run: cd jr && python3 -m pytest test_tick.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import ledger
import memory
import publish
import tick
from budget import Budget

NOW = datetime(2026, 9, 5, 4, 7, tzinfo=timezone.utc)
PROTECTION_RULE = json.dumps({"required_status_checks": {"contexts": ["schema", "tests", "jr-tests"]}})


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def recorder(script=None):
    calls, script = [], (script or {})

    def fn(*args):
        calls.append(args)
        norm = args[2:] if args[:1] == ("-C",) else args
        for prefix, (rc, out) in script.items():
            if norm[:len(prefix)] == prefix:
                return Proc(returncode=rc, stdout=out)
        return Proc()
    fn.calls = calls
    return fn


def norm(fn):
    return [a[2:] if a[:1] == ("-C",) else a for a in fn.calls]


def gh_ok(rate="4999", prs="[]", protection_rc=0, allow="true", pr_url="https://github.com/o/r/pull/1"):
    return recorder({
        ("api", "rate_limit"): (0, rate + "\n"),
        ("pr", "list"): (0, prs),
        ("api", "repos/o/r/branches/main/protection"): (protection_rc, PROTECTION_RULE if protection_rc == 0 else ""),
        ("api", "repos/o/r", "-q", ".allow_auto_merge"): (0, allow),
        ("pr", "create"): (0, pr_url + "\n"),
    })


def git_ok(wt_dir: Path, staged=True):
    return recorder({
        ("remote", "get-url", "origin"): (0, "https://github.com/o/r.git\n"),
        ("rev-parse", "origin/main"): (0, "6190d21abc\n"),
        ("status", "--porcelain"): (0, ""),
        ("diff", "--cached", "--quiet"): (1 if staged else 0, ""),
        ("diff", "--cached", "--name-status"): (0, "A\tdata/firmware/x/firmware.md\n"),
        ("rev-parse", "HEAD"): (0, "feedbee\n"),
    })


GAUGE = lambda d: {"entities": {"boards": {"pct": 42.5}}, "overall_pct": 68.2}  # noqa: E731
GUARD_OK = lambda root: {"ok": True, "output": ""}                               # noqa: E731


@pytest.fixture
def wt_dir(tmp_path, monkeypatch):
    """add_worktree is real code over the recorder git; pin its directory to tmp_path."""
    d = tmp_path / "wt"
    d.mkdir()
    (d / "jr").mkdir()
    monkeypatch.setattr(tick.publish.tempfile, "mkdtemp", lambda prefix="": str(d))
    return d


def run(**kw):
    kw.setdefault("now", NOW)
    kw.setdefault("gauge", GAUGE)
    kw.setdefault("guard", GUARD_OK)
    kw.setdefault("notifier", None)
    kw.setdefault("env", {})
    kw.setdefault("stages", [])
    kw.setdefault("budget", Budget(clock=lambda: 0.0))
    return tick.run_tick(**kw)


# --- dry run -----------------------------------------------------------------------------------

def test_dry_run_prints_gauge_allocation_and_nothing_to_do_and_writes_nothing(capsys, tmp_path):
    git, gh = git_ok(tmp_path), gh_ok()
    r = run(dry_run=True, git=git, gh=gh)
    out = capsys.readouterr().out
    assert not r.aborted
    assert "jr-tick (dry-run)" in out and "boards 42.5%" in out
    assert "boards 42.5% -> A0/B0 (phase 2: no content stages)" in out and "nothing to do" in out
    # read-only: no worktree, no add/commit/push, no PR, only read calls to gh
    assert all(c[0] not in ("worktree", "add", "commit", "push", "checkout") for c in norm(git))
    assert all(c[:2] in (("api", "rate_limit"), ("pr", "list"), ("api", "repos/o/r/branches/main/protection"),
                         ("api", "repos/o/r")) for c in gh.calls)
    assert r.memory == {} and any("dry-run" in w for w in r.warnings)


def test_dry_run_with_real_gauge_reads_the_repo_tree(tmp_path):
    if not (tick.REPO / "data" / "boards").is_dir():
        pytest.skip("tick.py is not inside the repo (scratch run)")
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), gauge=tick.default_gauge)
    assert not r.aborted and r.boards_pct is not None and 0 < r.boards_pct < 100


def test_dry_run_only_warns_when_protection_is_missing(tmp_path):
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(protection_rc=1))
    assert not r.aborted and any("branch protection" in w for w in r.warnings)


# --- preflight aborts --------------------------------------------------------------------------

def test_aborts_on_low_rate_limit_before_any_worktree(tmp_path):
    git = git_ok(tmp_path)
    r = run(git=git, gh=gh_ok(rate="120"))
    assert r.aborted == "GitHub rate limit low: 120 < 500"
    assert all(c[0] != "worktree" for c in norm(git))


def test_aborts_when_a_tick_pr_is_open_too_long(tmp_path):
    old = (NOW - timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    prs = json.dumps([{"number": 7, "createdAt": old, "headRefName": "jr/tick-20260905-0007"},
                      {"number": 8, "createdAt": old, "headRefName": "feat/human-branch"}])
    r = run(git=git_ok(tmp_path), gh=gh_ok(prs=prs))
    assert r.aborted.startswith("a Jr tick PR has been open > 3 h: #7")


def test_recent_tick_pr_does_not_abort(tmp_path, wt_dir):
    recent = (NOW - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    prs = json.dumps([{"number": 9, "createdAt": recent, "headRefName": "jr/tick-20260905-0337"}])
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=prs))
    assert not r.aborted


def test_real_run_aborts_red_when_main_is_unprotected(tmp_path):
    git = git_ok(tmp_path)
    r = run(git=git, gh=gh_ok(protection_rc=1))
    assert r.aborted.startswith("branch protection:")
    assert all(c[0] != "worktree" for c in norm(git))


def test_aborts_when_gh_is_unavailable(tmp_path):
    r = run(git=git_ok(tmp_path), gh=recorder({("api", "rate_limit"): (1, "")}))
    assert "gh unavailable" in r.aborted


# --- real run: worktree + memory + no stages ----------------------------------------------------

def test_real_quiet_run_uses_a_worktree_reconciles_memory_and_publishes_nothing(wt_dir):
    # a proposed record whose PR was closed → permanent rejection, written INSIDE the worktree
    lp = wt_dir / "jr" / "proposed_ledger.json"
    ledger.record_proposed("gone", "o/gone", pr_ref="https://github.com/o/r/pull/3", path=lp)
    git, gh = git_ok(wt_dir), gh_ok()
    reval_calls = []

    r = run(git=git, gh=gh, pr_state=lambda ref: "closed", revalidate=lambda s: reval_calls.append(s) or {"ok": True})

    assert not r.aborted
    assert r.base_sha == "6190d21"
    assert r.memory == {"expired": 0, "merged": 0, "rejected": 1, "removed": 0}
    assert memory.load(lp)["by_id"]["gone"]["status"] == "rejected"
    assert reval_calls == []                                   # nothing merged → no purge
    assert r.publish is None and "nothing to do" in tick.report.render_line(r)
    calls = norm(git)
    i = calls.index(("fetch", "origin", "main"))
    assert calls[i + 1] == ("worktree", "add", "--detach", str(wt_dir), "origin/main")
    assert all(c[0] != "worktree" for c in calls[:i])            # nothing before the fetch
    assert ("worktree", "remove", "--force", str(wt_dir)) in calls
    assert all(c[0] not in ("add", "commit", "push", "checkout") for c in calls)
    assert all(c[:2] != ("pr", "create") for c in gh.calls)


def test_merged_pr_triggers_the_catalog_purge_with_the_secret(wt_dir):
    lp = wt_dir / "jr" / "proposed_ledger.json"
    ledger.record_proposed("done", "o/done", pr_ref="https://github.com/o/r/pull/4", path=lp)
    seen = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(), env={"REVALIDATE_SECRET": "s3"},
            pr_state=lambda ref: "merged", revalidate=lambda s: seen.append(s) or {"ok": True, "status": 200})
    assert r.memory["merged"] == 1 and seen == ["s3"] and r.revalidate == {"ok": True, "status": 200}


# --- real run: a stage that writes -------------------------------------------------------------

def _stage(paths, needs_human=False, admitted=1, rejects=None):
    def stage(ctx):
        assert ctx.root and ctx.ledger_path == ctx.root / "jr" / "proposed_ledger.json"
        return tick.StageResult("fake", paths=paths, summary="wrote", needs_human=needs_human,
                                admitted=admitted, rejects=rejects or {})
    return stage


def test_stage_output_is_guarded_then_published_with_auto_merge(wt_dir):
    git, gh = git_ok(wt_dir), gh_ok()
    guard_calls = []
    r = run(git=git, gh=gh, stages=[_stage(["data/firmware/x"], rejects={"fork": 2})],
            guard=lambda root: guard_calls.append(root) or {"ok": True, "output": ""})
    assert not r.aborted and guard_calls == [wt_dir]
    assert r.admitted == 1 and r.rejects == {"fork": 2}
    assert r.publish["published"] and r.publish["auto_merge"] and r.publish["pr_url"] == "https://github.com/o/r/pull/1"
    calls = norm(git)
    assert ("add", "--", "data/firmware/x", "jr/proposed_ledger.json") in calls
    assert any(c[:3] == ("checkout", "-q", "-b") and c[3] == "jr/tick-20260905-0407" for c in calls)
    assert ("push", "-u", "origin", "jr/tick-20260905-0407") in calls
    assert gh.calls[-1] == ("pr", "merge", "https://github.com/o/r/pull/1", "--auto", "--squash")
    assert calls[-2:] == [("worktree", "remove", "--force", str(wt_dir)), ("worktree", "prune")]
    body = [c for c in gh.calls if c[:2] == ("pr", "create")][0]
    assert "- **fake** — wrote" in body[body.index("--body") + 1]


def test_needs_human_withholds_auto_merge(wt_dir):
    gh = gh_ok()
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_stage(["data/firmware/x"], needs_human=True)])
    assert r.publish["published"] and not r.publish["auto_merge"]
    assert all(c[:2] != ("pr", "merge") for c in gh.calls)


def test_guard_red_discards_the_worktree_and_publishes_nothing(wt_dir):
    git, gh = git_ok(wt_dir), gh_ok()
    r = run(git=git, gh=gh, stages=[_stage(["data/firmware/x"])], guard=lambda root: {"ok": False, "output": "boom"})
    assert r.aborted.startswith("guard red")
    calls = norm(git)
    assert all(c[0] not in ("add", "commit", "push", "checkout") for c in calls)
    assert ("worktree", "remove", "--force", str(wt_dir)) in calls
    assert all(c[:2] != ("pr", "create") for c in gh.calls)


def test_a_crashing_stage_is_reported_and_the_worktree_still_removed(wt_dir):
    def bad(ctx):
        raise KeyError("oops")
    git = git_ok(wt_dir)
    r = run(git=git, gh=gh_ok(), stages=[bad])
    assert r.aborted == "KeyError: 'oops'"
    assert ("worktree", "remove", "--force", str(wt_dir)) in norm(git)


def test_budget_exhaustion_aborts_cleanly(wt_dir):
    git = git_ok(wt_dir)
    r = run(git=git, gh=gh_ok(), budget=Budget(max_calls=2, clock=lambda: 0.0))
    assert r.aborted.startswith("budget:")
    assert r.budget.startswith("gh calls 2/2")
    # the abort hit during preflight, before any worktree, so nothing to remove
    assert all(c[0] != "worktree" for c in norm(git))


def test_dry_run_never_calls_the_notifier_and_real_run_does(wt_dir, tmp_path):
    sent = []
    run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), notifier=lambda t: sent.append(t))
    assert sent == []
    run(git=git_ok(wt_dir), gh=gh_ok(), notifier=lambda t: sent.append(t))
    assert len(sent) == 1 and sent[0].startswith("🤖 jr-tick 2026-09-05 04:07 UTC")


def test_a_failing_notifier_never_fails_the_tick(wt_dir):
    def boom(t):
        raise RuntimeError("telegram down")
    r = run(git=git_ok(wt_dir), gh=gh_ok(), notifier=boom)
    assert not r.aborted


# --- CLI ---------------------------------------------------------------------------------------

def test_main_exit_code_follows_aborted(monkeypatch):
    monkeypatch.setattr(tick, "run_tick", lambda **kw: tick.report.TickReport(when=NOW))
    assert tick.main(["--dry-run"]) == 0
    monkeypatch.setattr(tick, "run_tick", lambda **kw: tick.report.TickReport(when=NOW, aborted="x"))
    assert tick.main(["--dry-run", "--no-telegram", "--max-calls", "10"]) == 1


def test_stages_registry_is_empty_in_phase_two():
    assert tick.STAGES == []
