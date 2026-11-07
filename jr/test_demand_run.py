"""Tests for jr/demand_run.py — the daily demand runner (F2: demand never steered Jr because the
miner was never scheduled).

`git` and `gh` are ALWAYS recorders and the miner is a fake that writes into the worktree, so no
test runs a real git/gh command, the composio venv, or the network. The fake miner runs the REAL
pure pipeline (demand.build_demand_items + write_snapshot/write_unresolved) over fixture GSC rows,
so what lands is exactly what the live miner would write.

Run: cd jr && python3 -m pytest test_demand_run.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import demand
import demand_run

NOW = datetime(2026, 11, 3, 9, 30, 0, tzinfo=timezone.utc)
TODAY = "2026-11-03"
SLUG = "fcavalcantirj/esp-atlas"
FIRMWARE_IDS = {"launcher", "bruce", "esp32marauder", "m5stick-nemo"}
PART_IDS = {"esp32-c6", "esp32-s3"}


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def recorder(script=None):
    """A fake git/gh: `script` maps an argv prefix (after any `-C <dir>`) to (rc, stdout)."""
    calls = []
    script = script or {}

    def fn(*args):
        calls.append(args)
        norm = args[2:] if args[:1] == ("-C",) else args
        for prefix, (rc, out) in script.items():
            if norm[:len(prefix)] == prefix:
                return Proc(returncode=rc, stdout=out)
        return Proc()

    fn.calls = calls
    return fn


def norm_calls(fn):
    return [a[2:] if a[:1] == ("-C",) else a for a in fn.calls]


def git_ok():
    # `diff --cached --quiet` rc 1 = there IS something staged (publish proceeds); the staged diff is
    # the two demand snapshot paths, which jr/review_routing.py routes AUTO
    return recorder({("diff", "--cached", "--quiet"): (1, ""), ("rev-parse",): (0, "abc1234\n"),
                     ("diff", "--cached", "--name-status", "--no-renames", "-z"):
                         (0, "A\0docs/demand/2026-11-03.json\0M\0docs/demand/unresolved.json\0")})


def gh_ok(open_prs="[]"):
    return recorder({("pr", "create"): (0, "https://github.com/fcavalcantirj/esp-atlas/pull/1401\n"),
                     ("pr", "list"): (0, open_prs)})


# --- fixtures: GSC query rows in the raw Composio shape (firmware / board demand) ---------------

def _gsc(query, impressions, clicks=0, position=12.0):
    return {"keys": [query], "impressions": impressions, "clicks": clicks,
            "ctr": (clicks / impressions) if impressions else 0.0, "position": position}


GSC_ROWS = [
    _gsc("launcher esp32", 115, clicks=7, position=9.4),
    _gsc("esp32 marauder flash", 40, clicks=1, position=18.2),
    _gsc("esp32-c6", 134, clicks=1, position=31.7),
    _gsc("m5 stick s3", 11, position=12.5),
    _gsc("bruce firmware cardputer", 3),       # below the miner's floor: never an item
]


def _items(rows, today=TODAY):
    return demand.build_demand_items(rows, firmware_ids=FIRMWARE_IDS, part_ids=PART_IDS, today=today)


def _write_prev(wt: Path, date: str, items, window=None):
    """Seed the worktree's docs/demand/ with a committed snapshot (what origin/main carries)."""
    d = wt / "docs" / "demand"
    demand.write_snapshot(items, False, window or {"start": "2026-10-05", "end": date}, date, d)
    demand.write_unresolved(items, d)


def fake_miner(rows=GSC_ROWS, rc=0, today=TODAY):
    """Stands in for `<composio python> jr/demand.py` run inside the worktree."""
    seen = {}

    def miner(wt_path: Path, *, python: str, telegram: bool):
        seen.update(wt_path=wt_path, python=python, telegram=telegram)
        if rc == 0:
            items = _items(rows, today)
            d = wt_path / "docs" / "demand"
            demand.write_snapshot(items, False, {"start": "2026-10-06", "end": today}, today, d)
            demand.write_unresolved(items, d)
        return Proc(returncode=rc, stdout="", stderr="composio: 401" if rc else "")

    miner.seen = seen
    return miner


def run(wt, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_ok())
    kw.setdefault("miner", fake_miner())
    return demand_run.run(now=NOW, root=wt, repo_slug=SLUG, python="/venv/bin/python", **kw)


def _snap(date, items, window=None, version="v2"):
    return {"date": date, "window": window or {"start": "2026-10-01", "end": date},
            "weight_formula_version": version, "d2_available": False, "count": len(items), "items": items}


# --- (1) no-op detection -------------------------------------------------------------------------

def test_same_demand_with_only_date_fields_moved_is_a_noop():
    prev = _snap("2026-11-02", _items(GSC_ROWS, "2026-11-02"), {"start": "2026-10-05", "end": "2026-11-02"})
    new = _snap("2026-11-03", _items(GSC_ROWS, "2026-11-03"), {"start": "2026-10-06", "end": "2026-11-03"})
    assert prev != new                                   # date, window, first/last_seen all moved
    assert demand_run.is_noop(new, prev) is True


def test_a_changed_weight_or_a_new_item_is_not_a_noop():
    prev = _snap("2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    bumped = [dict(r) for r in GSC_ROWS]
    bumped[0]["impressions"] = 140
    assert demand_run.is_noop(_snap(TODAY, _items(bumped)), prev) is False
    more = GSC_ROWS + [_gsc("bruce firmware cardputer", 25)]
    assert demand_run.is_noop(_snap(TODAY, _items(more)), prev) is False


def test_a_formula_version_bump_is_not_a_noop():
    prev = _snap("2026-11-02", _items(GSC_ROWS, "2026-11-02"), version="v1")
    assert demand_run.is_noop(_snap(TODAY, _items(GSC_ROWS)), prev) is False


def test_no_previous_snapshot_is_never_a_noop():
    assert demand_run.is_noop(_snap(TODAY, _items(GSC_ROWS)), None) is False


def test_an_unchanged_snapshot_still_refreshes_before_the_loader_would_call_it_stale():
    # no-op only while the committed one is young: otherwise steady demand would go "stale"
    # after 14 days and stop steering — the very F2 bug.
    new = _snap(TODAY, _items(GSC_ROWS))
    young = _snap("2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    old = _snap("2026-10-27", _items(GSC_ROWS, "2026-10-27"))
    assert demand_run.should_land(new, young, TODAY) == (False, "no-op: demand unchanged since 2026-11-02")
    land, why = demand_run.should_land(new, old, TODAY)
    assert land is True and "refresh" in why


def test_the_runner_opens_no_pr_when_demand_is_unchanged(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    gh = gh_ok()
    res = run(tmp_path, gh=gh)
    assert res.published is False and res.reason.startswith("no-op")
    assert not any(c[:2] == ("pr", "create") for c in gh.calls)
    assert res.aborted == ""


def test_the_noop_run_neither_commits_nor_pushes(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    git = git_ok()
    run(tmp_path, git=git)
    verbs = [c[0] for c in norm_calls(git)]
    assert "commit" not in verbs and "push" not in verbs and "add" not in verbs


# --- landing through the tick's PR path -----------------------------------------------------------

def test_changed_demand_lands_both_files_on_a_demand_branch(tmp_path):
    _write_prev(tmp_path, "2026-09-09", _items(GSC_ROWS[:2], "2026-09-09"))
    git, gh = git_ok(), gh_ok()
    res = run(tmp_path, git=git, gh=gh)
    assert res.published is True and res.pr_url.endswith("/pull/1401")
    add = next(c for c in norm_calls(git) if c[:1] == ("add",))
    staged = list(add[2:])
    assert "docs/demand/2026-11-03.json" in staged and "docs/demand/unresolved.json" in staged
    assert not any(p.startswith("data/") for p in staged)          # bookkeeping only, no catalog
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    head = create[create.index("--head") + 1]
    assert head == "jr/demand-20261103-0930"                        # never the tick's jr/tick-*
    assert not head.startswith("jr/tick-")


def test_the_landed_snapshot_is_valid_and_steers(tmp_path):
    run(tmp_path)
    snap = json.loads((tmp_path / "docs" / "demand" / f"{TODAY}.json").read_text())
    assert snap["date"] == TODAY and snap["count"] == len(snap["items"]) > 0
    assert all(it["impressions"] >= demand.MIN_IMPRESSIONS for it in snap["items"] if it["impressions"])
    assert "bruce firmware cardputer" not in {it["term"] for it in snap["items"]}


def test_the_worktree_is_always_removed(tmp_path):
    git = git_ok()
    run(tmp_path, git=git)
    assert any(c[:2] == ("worktree", "remove") for c in norm_calls(git))


def test_an_older_open_demand_pr_is_closed_as_superseded_after_landing(tmp_path):
    prs = json.dumps([{"number": 1390, "headRefName": "jr/demand-20261102-0930",
                       "files": [{"path": "docs/demand/2026-11-02.json", "changeType": "ADDED"},
                                 {"path": "docs/demand/unresolved.json", "changeType": "MODIFIED"}], "changedFiles": 2},
                      {"number": 1399, "headRefName": "jr/tick-20261103-0900"}])
    gh = gh_ok(open_prs=prs)
    res = run(tmp_path, gh=gh)
    closes = [c for c in gh.calls if c[:2] == ("pr", "close")]
    assert [c[2] for c in closes] == ["1390"]                       # a tick PR is never touched
    assert res.superseded == [1390]


def test_a_jr_review_demand_pr_is_never_closed_as_superseded(tmp_path):
    manifest = {"files": [{"path": "docs/demand/2026-11-02.json", "changeType": "ADDED"}], "changedFiles": 1}
    prs = json.dumps([{"number": 1391, "headRefName": "jr/demand-20261101-0930", "labels": [{"name": "jr-review"}], **manifest},
                      {"number": 1392, "headRefName": "jr/demand-20261102-0930", "labels": [], **manifest}])
    gh = gh_ok(open_prs=prs)
    res = run(tmp_path, gh=gh)
    assert [c[2] for c in gh.calls if c[:2] == ("pr", "close")] == ["1392"] and res.superseded == [1392]


# --- failures never land anything -------------------------------------------------------------------

def test_a_failed_miner_aborts_without_a_pr(tmp_path):
    gh = gh_ok()
    res = run(tmp_path, gh=gh, miner=fake_miner(rc=1))
    assert res.published is False and res.aborted.startswith("miner failed (rc 1)")
    assert "composio: 401" in res.aborted
    assert not any(c[:2] == ("pr", "create") for c in gh.calls)


def test_an_empty_pull_is_treated_as_an_outage_not_as_zero_demand(tmp_path):
    _write_prev(tmp_path, "2026-09-09", _items(GSC_ROWS, "2026-09-09"))
    gh = gh_ok()
    res = run(tmp_path, gh=gh, miner=fake_miner(rows=[]))
    assert res.published is False and "no demand items" in res.aborted
    assert not any(c[:2] == ("pr", "create") for c in gh.calls)


def test_a_miner_that_writes_no_snapshot_aborts(tmp_path):
    res = run(tmp_path, miner=lambda wt, **kw: Proc(returncode=0))
    assert res.published is False and "no snapshot" in res.aborted


# --- Telegram is opt-in for this runner ------------------------------------------------------------

def test_telegram_defaults_off_and_is_opt_in(monkeypatch):
    seen = {}
    monkeypatch.setattr(demand_run, "run", lambda **kw: seen.update(kw) or demand_run.RunResult())
    demand_run.main([])
    assert seen["telegram"] is False
    demand_run.main(["--telegram"])
    assert seen["telegram"] is True


def test_the_miner_is_run_with_the_injected_python_and_no_telegram(tmp_path):
    miner = fake_miner()
    run(tmp_path, miner=miner)
    assert miner.seen == {"wt_path": tmp_path, "python": "/venv/bin/python", "telegram": False}


def test_main_reads_the_interpreter_from_jr_demand_python(monkeypatch):
    seen = {}
    monkeypatch.setattr(demand_run, "run", lambda **kw: seen.update(kw) or demand_run.RunResult())
    monkeypatch.setenv("JR_DEMAND_PYTHON", "/opt/composio/bin/python")
    demand_run.main([])
    assert seen["python"] == "/opt/composio/bin/python"
    monkeypatch.delenv("JR_DEMAND_PYTHON")
    demand_run.main([])
    assert seen["python"] == demand_run.DEFAULT_DEMAND_PYTHON == "/home/browbot/.composio-venv/bin/python"


def test_the_default_miner_passes_telegram_only_when_asked(monkeypatch, tmp_path):
    argvs = []
    monkeypatch.setattr(demand_run.subprocess, "run", lambda argv, **kw: argvs.append((argv, kw)) or Proc())
    demand_run.default_miner(tmp_path, python="/venv/bin/python", telegram=False)
    demand_run.default_miner(tmp_path, python="/venv/bin/python", telegram=True)
    assert argvs[0][0] == ["/venv/bin/python", "jr/demand.py"]
    assert argvs[1][0] == ["/venv/bin/python", "jr/demand.py", "--telegram"]
    assert argvs[0][1]["cwd"] == tmp_path                            # main's code, main's catalog


def test_the_default_miner_imports_the_worktrees_esp_atlas_core(monkeypatch, tmp_path):
    # the composio venv has no esp_atlas_core installed (jr/tools.py imports it): without this
    # the miner dies on import — and must read the WORKTREE's core and data, never the clone's
    seen = {}
    monkeypatch.setattr(demand_run.subprocess, "run", lambda argv, **kw: seen.update(kw) or Proc())
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    demand_run.default_miner(tmp_path, python="/venv/bin/python", telegram=False)
    env = seen["env"]
    assert env["PYTHONPATH"].split(":")[0] == str(tmp_path / "apps" / "core" / "src")
    assert env["ESP_ATLAS_REPO_ROOT"] == str(tmp_path)


def test_exit_code_is_nonzero_only_on_abort(monkeypatch):
    monkeypatch.setattr(demand_run, "run", lambda **kw: demand_run.RunResult(aborted="miner failed (rc 1)"))
    assert demand_run.main([]) == 1
    monkeypatch.setattr(demand_run, "run", lambda **kw: demand_run.RunResult(reason="no-op: x"))
    assert demand_run.main([]) == 0


def test_the_local_demand_branch_is_deleted_only_after_its_worktree_is_gone(tmp_path):
    git = git_ok()
    run(tmp_path, git=git)
    calls = norm_calls(git)
    remove = next(i for i, c in enumerate(calls) if c[:2] == ("worktree", "remove"))
    delete = next(i for i, c in enumerate(calls) if c[:2] == ("branch", "-D"))
    assert calls[delete] == ("branch", "-D", "jr/demand-20261103-0930") and delete > remove


def test_auto_merge_is_requested_through_the_same_protection_and_trust_gate(tmp_path, monkeypatch):
    import publish
    monkeypatch.setattr(publish, "protection_status", lambda slug, gh=None: publish.ProtectionStatus(
        True, ("schema", "tests", "jr-tests"), True))
    monkeypatch.setattr(publish, "trust_status", lambda gh=None: publish.TrustStatus(True, 10, 0))
    gh = gh_ok()
    res = run(tmp_path, gh=gh)
    assert res.auto_merge is True
    assert any(c[:5] == ("pr", "merge", "https://github.com/fcavalcantirj/esp-atlas/pull/1401",
                          "--auto", "--squash") and "--match-head-commit" in c for c in gh.calls)


def test_auto_merge_is_withheld_when_trust_is_not_earned(tmp_path, monkeypatch):
    import publish
    monkeypatch.setattr(publish, "protection_status", lambda slug, gh=None: publish.ProtectionStatus(
        True, ("schema", "tests", "jr-tests"), True))
    monkeypatch.setattr(publish, "trust_status", lambda gh=None: publish.TrustStatus(False, 3, 0, reason="3/10 clean merges"))
    gh = gh_ok()
    res = run(tmp_path, gh=gh)
    assert res.published is True and res.auto_merge is False and "3/10" in res.reason
    assert not any(c[:2] == ("pr", "merge") for c in gh.calls)


def test_a_miner_that_leaves_mains_snapshot_untouched_aborts(tmp_path):
    # main's committed snapshot is there; the miner exits 0 but writes nothing -> never mistake
    # the checked-out file for a fresh mine
    _write_prev(tmp_path, TODAY, _items(GSC_ROWS))
    gh = gh_ok()
    res = run(tmp_path, gh=gh, miner=lambda wt, **kw: Proc(returncode=0))
    assert res.published is False and "no snapshot" in res.aborted


def test_a_same_day_rerun_that_rewrites_identical_demand_is_a_noop(tmp_path):
    _write_prev(tmp_path, TODAY, _items(GSC_ROWS))
    res = run(tmp_path)
    assert res.aborted == "" and res.reason.startswith("no-op")


def test_a_failed_push_or_pr_is_an_abort_not_a_quiet_noop(tmp_path):
    git = recorder({("diff", "--cached", "--quiet"): (1, ""), ("push",): (1, ""), ("rev-parse",): (0, "abc1234\n")})
    res = run(tmp_path / "a", git=git)
    assert res.published is False and res.aborted == "publish failed: push failed"
    gh = recorder({("pr", "create"): (1, "")})
    res = run(tmp_path / "b", gh=gh)
    assert res.aborted == "publish failed: pr create failed"


def test_the_refresh_age_is_measured_between_the_miners_own_dates(tmp_path):
    # the miner dates in local time; a 21:30 -03 run is already "tomorrow" in UTC — the age must
    # come from the two snapshots' own dates, never mix clocks
    prev_items = _items(GSC_ROWS, "2026-10-28")
    _write_prev(tmp_path, "2026-10-28", prev_items)
    late = datetime(2026, 11, 4, 0, 30, tzinfo=timezone.utc)      # UTC day 7 after 10-28; local day 6
    res = demand_run.run(now=late, root=tmp_path, repo_slug=SLUG, python="/venv/bin/python",
                         git=git_ok(), gh=gh_ok(), miner=fake_miner(today="2026-11-03"))
    assert res.reason.startswith("no-op")
