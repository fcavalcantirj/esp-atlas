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
        ("pr", "list", "--author", "espatlas-jr"): (0, json.dumps([{"number": i, "mergedAt": "2026-09-05T00:00:00Z"} for i in range(10)])),   # trust earned
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
        ("diff", "--cached", "--name-status", "--no-renames", "-z"): (0, "A\0data/firmware/x/firmware.md\0"),
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


NO_SNAPSHOT = lambda root, date: (None, None, [])   # noqa: E731 — default: write no trend paths
NO_DEMAND = lambda root, date: None                 # noqa: E731 — default: no demand snapshot → no steer


def run(**kw):
    kw.setdefault("now", NOW)
    kw.setdefault("gauge", GAUGE)
    kw.setdefault("guard", GUARD_OK)
    kw.setdefault("notifier", None)
    kw.setdefault("snapshot", NO_SNAPSHOT)
    kw.setdefault("demand", NO_DEMAND)
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
    assert "boards 42.5% -> A0/B0 (no content stages registered)" in out and "nothing to do" in out
    # read-only: no worktree, no add/commit/push, no PR, only read calls to gh
    assert all(c[0] not in ("worktree", "add", "commit", "push", "checkout") for c in norm(git))
    assert all(c[:2] in (("api", "rate_limit"), ("pr", "list"), ("api", "repos/o/r/rules/branches/main"),
                         ("api", "repos/o/r/branches/main/protection"), ("api", "repos/o/r")) for c in gh.calls)
    assert r.memory == {} and any("dry-run" in w for w in r.warnings)


def _fake_stage_modules(monkeypatch, calls):
    import stage_admit
    import stage_boardmap
    import stage_backfill
    monkeypatch.setattr(stage_backfill, "run", lambda ctx, budget, fetch=None: calls.append(("backfill", budget)) or tick.StageResult("backfill", summary=f"backfilled {budget}"))
    monkeypatch.setattr(stage_boardmap, "run", lambda ctx, budget, only=None: calls.append(("boardmap", budget)) or tick.StageResult("boardmap", summary=f"mapped {budget}"))
    monkeypatch.setattr(stage_admit, "run", lambda ctx, budget, call_share=1.0: calls.append(("admit", budget, round(call_share, 2))) or tick.StageResult("admit", summary=f"scored {budget}"))


def test_hourly_path_runs_the_content_stages_from_the_split_heavier_first(capsys, tmp_path, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    r = run(git=git_ok(tmp_path), gh=gh_ok(), stages=None)   # None → hourly, not the manual override
    out = capsys.readouterr().out
    assert not r.aborted
    assert "boards 42.5% -> backfill 4 / firmware 2 (hourly)" in out   # allocate(42.5, 6): backfill-heavy (finite thin)
    # backfill runs first; firmware (2 units) → admit 1 + boardmap 1
    assert calls == [("backfill", 4), ("admit", 1, 0.5), ("boardmap", 1)]
    assert [s["name"] for s in r.stages] == ["backfill", "admit", "boardmap"]
    assert "backfilled 4" in out and "mapped 1" in out and "scored 1" in out


def test_hourly_stages_backfill_first_then_firmware_and_skip_empty_tracks(monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    for fn in tick.hourly_stages({"backfill": 4, "firmware": 2}):   # finite thin
        fn(None)
    assert calls == [("backfill", 4), ("admit", 1, 0.5), ("boardmap", 1)]
    calls.clear()
    for fn in tick.hourly_stages({"backfill": 2, "firmware": 4}):   # finite covered
        fn(None)
    assert calls == [("backfill", 2), ("admit", 2, 0.5), ("boardmap", 2)]
    calls.clear()
    for fn in tick.hourly_stages({"backfill": 3, "firmware": 0}):   # firmware track empty
        fn(None)
    assert calls == [("backfill", 3)]
    calls.clear()
    for fn in tick.hourly_stages({"backfill": 0, "firmware": 3}):   # backfill track empty; boardmap takes odd unit
        fn(None)
    assert calls == [("admit", 1, 0.33), ("boardmap", 2)]
    assert tick.hourly_stages({"backfill": 0, "firmware": 0}) == []


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

def test_real_run_with_a_memory_change_uses_a_worktree_and_ships_the_ledger_only(wt_dir):
    # a proposed record whose PR was closed → permanent rejection, written INSIDE the worktree,
    # and shipped as a ledger-only PR (no data paths, so no guard)
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
    assert r.guard is None                                     # no data written → no guard
    assert r.publish["published"] and r.publish["paths"] == ["jr/proposed_ledger.json"]
    calls = norm(git)
    i = calls.index(("fetch", "origin", "main"))
    assert calls[i + 1] == ("worktree", "prune")
    assert calls[i + 2] == ("worktree", "add", "--detach", str(wt_dir), "origin/main")
    assert all(c[0] != "worktree" for c in calls[:i])            # nothing before the fetch
    assert ("worktree", "remove", "--force", str(wt_dir)) in calls
    assert ("add", "--", "jr/proposed_ledger.json") in calls


def test_truly_quiet_run_publishes_nothing(wt_dir):
    git, gh = git_ok(wt_dir), gh_ok()
    r = run(git=git, gh=gh, pr_state=lambda ref: "open")
    assert not r.aborted and r.memory == {"expired": 0, "merged": 0, "rejected": 0, "removed": 0}
    assert r.publish is None and "nothing to do" in tick.report.render_line(r)
    calls = norm(git)
    assert all(c[0] not in ("add", "commit", "push", "checkout") for c in calls)
    assert ("worktree", "remove", "--force", str(wt_dir)) in calls
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
    assert any(c[:3] == ("checkout", "-q", "-B") and c[3] == "jr/tick-20260905-0407" for c in calls)
    assert ("push", "-u", "origin", "jr/tick-20260905-0407") in calls
    assert gh.calls[-1] == ("pr", "merge", "https://github.com/o/r/pull/1", "--auto", "--squash")
    assert calls[-3:] == [("worktree", "remove", "--force", str(wt_dir)), ("worktree", "prune"),
                          ("branch", "-D", "jr/tick-20260905-0407")]
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


# --- data-quality trend snapshot (SPEC-data-trend.md) ------------------------------------------

def test_non_dry_run_writes_the_trend_and_commits_it(wt_dir):
    """A real tick writes docs/telemetry/data-trend.jsonl into the worktree, includes it (and the
    dated md) in the commit pathspec, and stores the row+delta on the report."""
    calls = []

    def snap(root, date):
        calls.append((root, date))
        (root / "docs" / "telemetry").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "telemetry" / "data-trend.jsonl").write_text('{"date":"%s"}\n' % date)
        (root / "docs" / "telemetry" / f"data-{date}.md").write_text("# snap\n")
        return {"date": date, "finite_overall_pct": 41.2, "board_fields": {"usb_serial": {"count": 5}}}, None, \
            ["docs/telemetry/data-trend.jsonl", f"docs/telemetry/data-{date}.md"]

    git = git_ok(wt_dir)
    r = run(git=git, gh=gh_ok(), snapshot=snap)
    assert not r.aborted
    assert calls == [(wt_dir, "2026-09-05")]
    assert (wt_dir / "docs" / "telemetry" / "data-trend.jsonl").exists()
    assert "docs/telemetry/data-trend.jsonl" in r.paths
    assert ("add", "--", "docs/telemetry/data-trend.jsonl",
            "docs/telemetry/data-2026-09-05.md", "jr/proposed_ledger.json") in norm(git)
    assert r.data_row["finite_overall_pct"] == 41.2 and r.data_delta is None


def test_dry_run_does_not_write_the_trend(tmp_path):
    calls = []
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(),
            snapshot=lambda root, date: calls.append((root, date)) or (None, None, []))
    assert not r.aborted and calls == []          # snapshot never called on a dry run
    assert r.data_row is None and "docs/telemetry/data-trend.jsonl" not in r.paths


def test_a_failing_snapshot_warns_but_never_aborts(wt_dir):
    def boom(root, date):
        raise RuntimeError("disk full")
    r = run(git=git_ok(wt_dir), gh=gh_ok(), snapshot=boom)
    assert not r.aborted and any("data snapshot failed" in w for w in r.warnings)
    assert r.data_row is None


# --- demand steering (SPEC-demand-steering.md) -------------------------------------------------

def _demand_snap(stale=False, age_days=0, items=None, date="2026-09-05"):
    """A load_latest-shaped return: a docs/demand snapshot + computed stale/age_days."""
    items = items if items is not None else []
    return {"date": date, "stale": stale, "age_days": age_days,
            "window": {"start": "2026-08-08", "end": date}, "count": len(items), "items": items}


# one UNCOVERED firmware gap (steers toward Track B) + a RANKS_POORLY SEO row (must NOT steer)
DEMAND_ITEMS = [
    {"term": "m5stack stick s3", "gap": "UNCOVERED", "weight": 27.0, "impressions": 11, "ctr": 0.0,
     "position": 24.5, "resolved": {"board": "m5stick-s3", "chip": "esp32-s3",
                                    "firmware_token": "m5stack-avatar-mic", "capability": [], "part": None}},
    {"term": "esp32-c6", "gap": "RANKS_POORLY", "weight": 421.59, "impressions": 134, "ctr": 0.0075,
     "position": 31.7, "resolved": {"board": None, "chip": "esp32-c6", "firmware_token": None,
                                    "capability": [], "part": "esp32-c6"}},
]


def test_fresh_demand_snapshot_steers_the_split_and_populates_alignment(capsys, tmp_path, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    r = run(git=git_ok(tmp_path), gh=gh_ok(), stages=None,
            demand=lambda root, today: _demand_snap(items=DEMAND_ITEMS))
    out = capsys.readouterr().out
    assert not r.aborted
    assert r.demand_signal is not None and r.demand_signal["bias"] > 0.0      # firmware demand → toward Track B
    # base at boards 42.5% is {4,2}; the +bias moves one unit to firmware → {3,3}
    assert "backfill 3 / firmware 3 (hourly)" in out
    assert r.alignment is not None and r.alignment["uncovered"] == 1
    body = tick.report.render_pr_body(r)
    assert "### Demand alignment" in body
    assert "m5stack stick s3" in body                                          # UNCOVERED → Jr worklist
    assert "RANKS_POORLY (SEO" in body and "esp32-c6" in body                  # SEO list, labelled NOT authoring


def test_stale_demand_snapshot_does_not_steer_and_reports_honestly(capsys, tmp_path, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    r = run(git=git_ok(tmp_path), gh=gh_ok(), stages=None,
            demand=lambda root, today: _demand_snap(stale=True, age_days=40, items=DEMAND_ITEMS))
    out = capsys.readouterr().out
    assert not r.aborted
    assert r.demand_signal is None and r.alignment is None                     # stale → no steer
    assert "backfill 4 / firmware 2 (hourly)" in out                          # unbiased base
    body = tick.report.render_pr_body(r)
    assert "stale" in body and "not steering" in body


def test_missing_demand_snapshot_behaves_exactly_as_today(capsys, tmp_path, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    r = run(git=git_ok(tmp_path), gh=gh_ok(), stages=None, demand=lambda root, today: None)
    out = capsys.readouterr().out
    assert not r.aborted
    assert r.demand_signal is None and r.alignment is None and r.demand_meta is None
    assert "backfill 4 / firmware 2 (hourly)" in out


def test_a_failing_demand_loader_warns_but_never_aborts(tmp_path, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)

    def boom(root, today):
        raise RuntimeError("demand read blew up")
    r = run(git=git_ok(tmp_path), gh=gh_ok(), stages=None, demand=boom)
    assert not r.aborted and any("demand" in w for w in r.warnings)
    assert r.demand_signal is None


# --- CLI ---------------------------------------------------------------------------------------

def test_main_exit_code_follows_aborted(monkeypatch):
    monkeypatch.setattr(tick, "run_tick", lambda **kw: tick.report.TickReport(when=NOW))
    assert tick.main(["--dry-run"]) == 0
    monkeypatch.setattr(tick, "run_tick", lambda **kw: tick.report.TickReport(when=NOW, aborted="x"))
    assert tick.main(["--dry-run", "--no-telegram", "--max-calls", "10"]) == 1


def test_stages_registry_is_empty_in_phase_two():
    assert tick.STAGES == []


# --- review-driven guards (adversarial review of the tick branch) ------------------------------

def test_a_ledger_only_change_is_published_without_running_the_guard(wt_dir):
    """Memory reconciliation must ship even when no stage wrote, or it dies with the worktree
    and every hourly tick redoes it. No data changed, so validate.py is skipped."""
    lp = wt_dir / "jr" / "proposed_ledger.json"
    ledger.record_proposed("done", "o/done", pr_ref="https://github.com/o/r/pull/4", path=lp)
    git, gh, guard_calls = git_ok(wt_dir), gh_ok(), []
    r = run(git=git, gh=gh, pr_state=lambda ref: "merged", revalidate=lambda s: {"ok": True},
            guard=lambda root: guard_calls.append(root) or {"ok": True, "output": ""})
    assert not r.aborted and guard_calls == [] and r.guard is None
    assert r.publish["published"] and r.publish["auto_merge"]
    calls = norm(git)
    assert ("add", "--", "jr/proposed_ledger.json") in calls
    subject = [c for c in calls if c[:1] == ("commit",)][0][-1]
    assert subject.startswith("chore(jr): tick") and "memory reconciliation" in subject


def test_a_pr_merged_after_the_fetch_is_not_rejected_as_removed(wt_dir):
    """Race: the PR settled as merged by gh is catalogued on GitHub but not yet in the worktree."""
    lp = wt_dir / "jr" / "proposed_ledger.json"
    ledger.record_proposed("racy", "o/racy", pr_ref="https://github.com/o/r/pull/5", path=lp)
    r = run(git=git_ok(wt_dir), gh=gh_ok(), pr_state=lambda ref: "merged", revalidate=lambda s: {"ok": True})
    assert r.memory == {"expired": 0, "merged": 1, "rejected": 0, "removed": 0}
    assert memory.load(lp)["by_id"]["racy"]["status"] == "merged"


def test_stale_pr_query_failure_aborts_closed(tmp_path):
    gh = recorder({("api", "rate_limit"): (0, "4999"), ("pr", "list"): (1, "")})
    r = run(git=git_ok(tmp_path), gh=gh)
    assert r.aborted == "gh pr list failed (cannot see open Jr PRs)"


def test_a_failing_worktree_removal_is_a_warning_not_a_lost_report(wt_dir, capsys):
    base = git_ok(wt_dir)

    def git(*args):
        if args[:2] == ("worktree", "remove"):
            raise OSError("fork failed")
        return base(*args)
    git.calls = base.calls
    r = run(git=git, gh=gh_ok())
    assert not r.aborted and any("worktree cleanup failed" in w for w in r.warnings)
    assert "jr-tick 2026-09-05 04:07 UTC" in capsys.readouterr().out


def test_publish_gets_the_uncounted_gh_so_budget_cannot_cut_it_off_mid_publish(wt_dir):
    gh = gh_ok()
    # preflight = rate_limit + pr list + rules + protection + allow_auto_merge = 5 counted calls; the budget
    # is exactly that, so publish's own pr create / pr merge would die if they were counted
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_stage(["data/firmware/x"])], budget=Budget(max_calls=5, clock=lambda: 0.0))
    assert not r.aborted and r.publish["published"] and r.publish["auto_merge"]
    assert r.budget.startswith("gh calls 5/5")


def test_guard_env_points_core_at_the_worktree(tmp_path):
    env = tick.guard_env(tmp_path, base={"PATH": "/usr/bin", "PYTHONPATH": "/x"})
    assert env["ESP_ATLAS_REPO_ROOT"] == str(tmp_path)
    assert env["PYTHONPATH"].split(tick.os.pathsep) == [str(tmp_path / "apps" / "core" / "src"), "/x"]
    assert env["PATH"] == "/usr/bin"


def test_default_guard_runs_validate_in_the_worktree_env_and_skips_the_slow_tests_by_default(tmp_path, monkeypatch):
    runs = []

    def fake_run(argv, **kw):
        runs.append((argv, kw))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(tick.subprocess, "run", fake_run)
    monkeypatch.delenv("JR_GUARD_TESTS", raising=False)
    res = tick.default_guard(tmp_path)
    assert res["ok"] and "guard tests skipped" in res["output"]
    assert len(runs) == 1 and runs[0][0][1:] == ["scripts/validate.py"] and runs[0][1]["cwd"] == tmp_path
    assert runs[0][1]["env"]["ESP_ATLAS_REPO_ROOT"] == str(tmp_path)


def test_default_guard_runs_the_ci_tests_only_when_asked(tmp_path, monkeypatch):
    runs = []

    def fake_run(argv, **kw):
        runs.append((argv, kw))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(tick.subprocess, "run", fake_run)
    monkeypatch.setenv("JR_GUARD_TESTS", "1")
    assert tick.default_guard(tmp_path) == {"ok": True, "output": "ok"}
    assert runs[0][0][1:] == ["scripts/validate.py"] and runs[1][0][1:3] == ["-m", "pytest"] and runs[1][1]["cwd"] == tmp_path
    for _, kw in runs:
        assert kw["env"]["ESP_ATLAS_REPO_ROOT"] == str(tmp_path)


def test_main_installs_a_sigterm_handler_that_aborts_instead_of_dying(monkeypatch):
    import signal
    monkeypatch.setattr(tick, "run_tick", lambda **kw: tick.report.TickReport(when=NOW))
    tick.main(["--dry-run"])
    handler = signal.getsignal(signal.SIGTERM)
    assert handler is tick._on_sigterm
    with pytest.raises(tick.TickAbort):
        handler(signal.SIGTERM, None)


# --- manual tracks (Phases 3-4) ----------------------------------------------------------------------

def test_stages_for_tracks_build_admit_and_boardmap_stages_and_rejects_unknown_tracks():
    import stage_admit
    import stage_boardmap
    assert tick.stages_for(None, 3) is None
    stages = tick.stages_for("b", 2)
    assert len(stages) == 1 and callable(stages[0])
    stages = tick.stages_for("A", 1)
    assert len(stages) == 1 and callable(stages[0])   # Phase 3 fills it: the admit stage, hand-driven
    stages = tick.stages_for("a", 1)
    assert len(stages) == 1 and callable(stages[0])
    with pytest.raises(SystemExit):
        tick.stages_for("Z", 1)


def test_stages_for_track_a_stage_calls_stage_admit_with_the_budget(monkeypatch):
    import stage_admit
    seen = {}
    monkeypatch.setattr(stage_admit, "run",
                        lambda ctx, budget=3: seen.update(ctx=ctx, budget=budget) or "STAGE-RESULT")
    sentinel = object()
    assert tick.stages_for("A", 2)[0](sentinel) == "STAGE-RESULT"
    assert seen == {"ctx": sentinel, "budget": 2}


def test_main_track_a_passes_the_admit_stage_and_still_reports(monkeypatch):
    seen = {}

    def fake_run(**kw):
        seen.update(kw)
        return tick.report.TickReport(when=NOW)
    monkeypatch.setattr(tick, "run_tick", fake_run)
    assert tick.main(["--dry-run", "--track", "A", "--no-telegram"]) == 0
    assert len(seen["stages"]) == 1


def test_main_passes_track_and_budget_to_run_tick(monkeypatch):
    seen = {}

    def fake_run(**kw):
        seen.update(kw)
        return tick.report.TickReport(when=NOW)
    monkeypatch.setattr(tick, "run_tick", fake_run)
    assert tick.main(["--dry-run", "--track", "B", "--budget", "2", "--no-telegram"]) == 0
    assert seen["dry_run"] is True and len(seen["stages"]) == 1 and seen["telegram"] is False


def test_main_firmware_and_no_auto_merge_flags_reach_the_stage_and_run_tick(monkeypatch):
    seen = {}

    def fake_run(**kw):
        seen.update(kw)
        return tick.report.TickReport(when=NOW)
    monkeypatch.setattr(tick, "run_tick", fake_run)
    called = {}
    import stage_boardmap
    monkeypatch.setattr(stage_boardmap, "run", lambda ctx, budget, only=None: called.update(budget=budget, only=only) or tick.StageResult("boardmap"))
    assert tick.main(["--dry-run", "--track", "B", "--budget", "2", "--firmware", "wled, bruce", "--no-auto-merge", "--no-telegram"]) == 0
    assert seen["auto_merge"] is False and len(seen["stages"]) == 1
    seen["stages"][0](None)
    assert called == {"budget": 2, "only": ["wled", "bruce"]}
    with pytest.raises(SystemExit):
        tick.main(["--dry-run", "--track", "A", "--firmware", "wled", "--no-telegram"])      # --firmware is Track B only
