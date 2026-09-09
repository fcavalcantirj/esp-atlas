"""Tests for the open-PR ledger hydration (jr/tick.py) — the duplicate-PR fix.

Root cause: a tick starts from a fresh `git worktree` detached at origin/main (jr/publish.py),
so it reads main's committed jr/proposed_ledger.json — which does NOT carry the `proposed`
entries an un-merged tick PR recorded on its own branch. Without hydration, jr/stage_admit's
dedup gate cannot see firmware already sitting in an open PR and re-authors it, opening a
DUPLICATE PR one hour later (observed live: #158/#159 and #162/#163 were identical re-proposals).

These tests run entirely on recorders: git/gh are scripted, gauge/guard/notifier are fakes, and
the "worktree" is a tmp_path carrying a copy of the real data/boards + data/modules (the admit
stage resolves chips against the tree it writes). No git, gh, validate.py or network is touched.

Run: cd jr && python3 -m pytest test_tick_hydration.py -v
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import ledger
import memory
import stage_admit
import tick
import tools
from budget import Budget

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 8, 5, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
PROTECTION_RULE = json.dumps({"required_status_checks": {"contexts": ["schema", "tests", "jr-tests"]}})

# One real-ish tick PR (the previous hour's un-merged proposal) whose changed files add a new
# firmware record + its first recipe — exactly what an admit tick writes.
OPEN_PR_NUMBER = 158
OPEN_PR = [{"number": OPEN_PR_NUMBER, "createdAt": RECENT, "headRefName": "jr/tick-20260908-0400"}]
PR_FILES = json.dumps({"files": [
    {"path": "data/firmware/newtool/firmware.md"},
    {"path": "data/firmware/newtool/signals.json"},
    {"path": "data/recipes/m5cardputer__newtool/recipe.md"},
]})


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


def git_ok(wt_dir: Path):
    return recorder({
        ("remote", "get-url", "origin"): (0, "https://github.com/o/r.git\n"),
        ("rev-parse", "origin/main"): (0, "6190d21abc\n"),
        ("status", "--porcelain"): (0, ""),
        ("diff", "--cached", "--quiet"): (1, ""),   # something staged
        ("diff", "--cached", "--name-status", "--no-renames", "-z"): (0, "A\0data/firmware/newtool/firmware.md\0"),
        ("rev-parse", "HEAD"): (0, "feedbee\n"),
    })


def gh(prs="[]", pr_files=PR_FILES):
    return recorder({
        ("api", "rate_limit"): (0, "4999\n"),
        ("pr", "list", "--author", "espatlas-jr"): (0, json.dumps([{"number": i, "mergedAt": "2026-09-08T00:00:00Z"} for i in range(10)])),
        ("pr", "list"): (0, prs),
        ("api", "repos/o/r/branches/main/protection"): (0, PROTECTION_RULE),
        ("api", "repos/o/r", "-q", ".allow_auto_merge"): (0, "true"),
        ("pr", "view", str(OPEN_PR_NUMBER), "--json", "files"): (0, pr_files),
        # The admit stage should NEVER reach this fetch when the id is already proposed — a
        # separate assertion proves the dedup happens before the meta fetch.
        ("api", "repos/n/newtool"): (0, json.dumps({
            "full_name": "n/newtool", "description": "A Cardputer tool", "license": {"spdx_id": "MIT"},
            "topics": [], "homepage": None, "default_branch": "main", "stargazers_count": 30,
            "archived": False, "forks_count": 2, "id": 4242, "fork": False, "source": None,
            "parent": None, "pushed_at": "2026-09-01T00:00:00Z", "language": "C"})),
        ("pr", "create"): (0, "https://github.com/o/r/pull/159\n"),
        ("pr", "merge"): (0, ""),
    })


GAUGE = lambda d: {"entities": {"boards": {"pct": 42.5}}, "overall_pct": 68.2}  # noqa: E731
GUARD_OK = lambda root: {"ok": True, "output": ""}                               # noqa: E731

LAUNCHER = [{"name": "My Cardputer Tool", "description": "A Cardputer tool", "category": "cardputer",
             "github": "https://github.com/n/newtool", "download": 100}]


@pytest.fixture
def wt(tmp_path, monkeypatch):
    """A worktree tmp dir with the real boards/modules the admit stage resolves chips against."""
    d = tmp_path / "wt"
    shutil.copytree(REPO / "data" / "boards", d / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", d / "data" / "modules")
    (d / "data" / "firmware").mkdir(parents=True)
    (d / "data" / "recipes").mkdir()
    (d / "jr").mkdir()
    monkeypatch.setattr(tick.publish.tempfile, "mkdtemp", lambda prefix="": str(d))
    return d


def _run(wt_dir, prs, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("gauge", GAUGE)
    kw.setdefault("guard", GUARD_OK)
    kw.setdefault("notifier", None)
    kw.setdefault("snapshot", lambda root, date: (None, None, []))   # trend snapshot tested in test_tick.py
    kw.setdefault("env", {})
    kw.setdefault("budget", Budget(clock=lambda: 0.0))
    kw.setdefault("auto_merge", False)
    g = gh(prs=prs)
    kw["gh"] = g
    r = tick.run_tick(git=git_ok(wt_dir), stages=[lambda ctx: stage_admit.run(ctx, budget=3)], **kw)
    return r, g


# --- unit: the hydration helper ----------------------------------------------------------------

def test_hydrate_open_pr_ledger_marks_open_pr_firmware_proposed(tmp_path):
    lp = tmp_path / "proposed_ledger.json"
    g = gh(prs=json.dumps(OPEN_PR))
    hydrated = tick.hydrate_open_pr_ledger(g, NOW, lp)
    assert hydrated == ["newtool"]
    rec = memory.load(lp)["by_id"]["newtool"]
    assert rec["status"] == "proposed" and rec["pr_ref"] == f"#{OPEN_PR_NUMBER}"
    assert memory.is_blocked(memory.load(lp), firmware_id="newtool", now=NOW)


def test_hydrate_open_pr_ledger_ignores_non_tick_branches_and_no_prs(tmp_path):
    lp = tmp_path / "proposed_ledger.json"
    human = json.dumps([{"number": 5, "createdAt": RECENT, "headRefName": "feat/human-branch"}])
    assert tick.hydrate_open_pr_ledger(gh(prs=human), NOW, lp) == []
    assert tick.hydrate_open_pr_ledger(gh(prs="[]"), NOW, lp) == []
    assert not lp.exists()   # nothing to hydrate → nothing written


def test_hydrate_open_pr_ledger_never_downgrades_a_human_veto(tmp_path):
    lp = tmp_path / "proposed_ledger.json"
    memory.record_rejected("newtool", "n/newtool", "PR closed unmerged", ttl_days=None, path=lp, now=NOW)
    tick.hydrate_open_pr_ledger(gh(prs=json.dumps(OPEN_PR)), NOW, lp)
    assert memory.load(lp)["by_id"]["newtool"]["status"] == "rejected"   # permanent veto survives


def test_hydrate_open_pr_ledger_never_downgrades_a_merged_record(tmp_path):
    """#181: a backfill PR re-touches an already-merged firmware id; hydration must leave that
    record `merged`, never turn it back into a fresh `proposed` (the merged->proposed downgrade
    scripts/ledger_guard.py blocks in CI)."""
    lp = tmp_path / "proposed_ledger.json"
    memory.record_proposed("newtool", "n/newtool", pr_ref="#100", path=lp, now=NOW)
    ledger.update_status("newtool", "merged", path=lp, now=NOW.isoformat())
    tick.hydrate_open_pr_ledger(gh(prs=json.dumps(OPEN_PR)), NOW, lp)
    rec = memory.load(lp)["by_id"]["newtool"]
    assert rec["status"] == "merged"     # NOT downgraded to proposed
    assert rec["pr_ref"] == "#100"       # the merge PR link preserved


# --- integration: run_tick does not re-author firmware already in an open PR --------------------

def test_run_tick_skips_firmware_already_in_an_open_pr(wt, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: list(LAUNCHER))
    r, g = _run(wt, prs=json.dumps(OPEN_PR))
    assert not r.aborted
    assert r.hydrated == ["newtool"]
    assert r.admitted == 0
    assert r.rejects.get("already_proposed") == 1
    assert not (wt / "data" / "firmware" / "newtool" / "firmware.md").exists()   # NOT re-authored
    assert r.publish is None                                                     # nothing new to ship
    # the dedup fires BEFORE the repo-meta fetch, so no wasted GitHub call
    assert all(c[:2] != ("api", "repos/n/newtool") for c in g.calls)


def test_run_tick_authors_when_no_open_pr(wt, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: list(LAUNCHER))
    r, g = _run(wt, prs="[]")
    assert not r.aborted
    assert r.hydrated == []
    assert r.admitted == 1
    assert (wt / "data" / "firmware" / "newtool" / "firmware.md").exists()       # authored as before
    assert any(c[:2] == ("api", "repos/n/newtool") for c in g.calls)             # meta WAS fetched
