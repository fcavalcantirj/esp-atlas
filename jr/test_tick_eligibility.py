"""Tick-PR eligibility gates the whole preflight, not just the pending index (PR 1512, R2j follow-up).

pending_prs.load reads only the Jr bot's own same-repo jr/tick-* PR, but the tick still selected PRs by
branch prefix alone in three other places. Anyone can name a fork's branch jr/tick-*, so a foreign-author,
fork or unknown-head PR (1) aborted the tick as a stale content PR, (2) was closed with --delete-branch as a
stale bookkeeping PR, and (3) was hydrated into the ledger as `proposed` — its victim firmware blocked for
every stage. An ineligible PR contributes nothing; the Jr bot's own same-repo PR keeps every behaviour.

Recorders only (test_tick's gh_with_prs). Run: cd jr && python3 -m pytest test_tick_eligibility.py -v
"""
from __future__ import annotations

import pytest

import memory
import tick
from publish import JR_LOGIN
from test_tick import BOOKKEEPING, FRESH, STALE, _closes, gh_with_prs, git_ok, run, wt_dir  # noqa: F401 — a fixture

BOT = {"login": JR_LOGIN}
INELIGIBLE = {
    "foreign author": {"author": {"login": "mallory"}, "isCrossRepository": False},
    "fork": {"author": BOT, "isCrossRepository": True},
    "unknown head repo": {"author": BOT},
}
ELIGIBLE = {"author": BOT, "isCrossRepository": False}
VICTIM_RECIPE = "data/recipes/b__victim/recipe.md"


def _pr(number, created, who, mergeable="MERGEABLE"):
    return {"number": number, "createdAt": created, "headRefName": f"jr/tick-20260905-{number:04d}",
            "mergeable": mergeable, **who}


def _blocked_probe(seen):
    def probe(ctx):
        seen.append(memory.is_blocked(memory.load(ctx.ledger_path), firmware_id="victim", now=ctx.now))
        return tick.StageResult("probe")
    return probe


@pytest.mark.parametrize("who", INELIGIBLE.values(), ids=INELIGIBLE.keys())
def test_an_ineligible_stale_content_pr_never_aborts_the_tick(wt_dir, who):
    gh = gh_with_prs([_pr(1600, STALE, who, "CONFLICTING")], files={1600: [VICTIM_RECIPE]})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted, r.aborted
    assert _closes(gh) == []


def test_an_eligible_stale_content_pr_still_aborts_naming_it(wt_dir):
    gh = gh_with_prs([_pr(1600, STALE, ELIGIBLE, "CONFLICTING")], files={1600: [VICTIM_RECIPE]})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert r.aborted.startswith("a Jr tick PR has been open > 3 h: #1600") and "needs a human" in r.aborted
    assert _closes(gh) == []


@pytest.mark.parametrize("who", INELIGIBLE.values(), ids=INELIGIBLE.keys())
def test_an_ineligible_stale_bookkeeping_pr_is_never_closed(wt_dir, who):
    gh = gh_with_prs([_pr(1601, STALE, who, "CONFLICTING")], files={1601: BOOKKEEPING})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted, r.aborted
    assert _closes(gh) == [] and not any("superseded" in w for w in r.warnings)


def test_an_eligible_stale_bookkeeping_pr_is_still_closed(wt_dir):
    gh = gh_with_prs([_pr(1601, STALE, ELIGIBLE, "CONFLICTING")], files={1601: BOOKKEEPING})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and [c[2] for c in _closes(gh)] == ["1601"]
    assert "--delete-branch" in _closes(gh)[0]


@pytest.mark.parametrize("who", INELIGIBLE.values(), ids=INELIGIBLE.keys())
def test_an_ineligible_recent_recipe_pr_hydrates_nothing(wt_dir, who):
    seen = []
    gh = gh_with_prs([_pr(1602, FRESH, who)], files={1602: [VICTIM_RECIPE]})   # its source read 404s
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_blocked_probe(seen)])
    assert not r.aborted, r.aborted
    assert r.hydrated == [] and seen == [False]
    assert "victim" not in memory.load(wt_dir / "jr" / "proposed_ledger.json")["by_id"]


def test_an_eligible_recent_recipe_pr_still_holds_its_firmware(wt_dir):
    seen = []
    gh = gh_with_prs([_pr(1602, FRESH, ELIGIBLE)], files={1602: [VICTIM_RECIPE]})
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_blocked_probe(seen)])
    assert not r.aborted, r.aborted
    assert r.hydrated == ["victim"] and seen == [True]
