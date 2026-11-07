"""Tests for jr/pending_prs.py — what Jr's own tick PRs already hold, read from GitHub's file lists.

Fake gh only: every answer is scripted. Run: cd jr && python3 -m pytest test_pending_prs.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pending_prs

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _pr(number, paths, branch="jr/tick-20261107-0300", **kw):
    return {"number": number, "headRefName": branch, "files": [{"path": p} for p in paths], **kw}


OPEN = _pr(1500, ["data/firmware/nightdriverstrip/firmware.md", "data/firmware/nightdriverstrip/signals.json",
                  "data/recipes/m5stick-c__nightdriverstrip/recipe.md", "data/recipes/m5cardputer__newtool/recipe.md",
                  "jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"])

NEWTOOL_PR_FILES = ["data/firmware/newtool/firmware.md", "data/recipes/m5cardputer__newtool/recipe.md"]   # an admit ships both


def _gh(closed=(), rc=0, calls=None):
    def gh(*a):
        if calls is not None:
            calls.append(a)
        return SimpleNamespace(returncode=rc, stdout=json.dumps(list(closed)) if rc == 0 else "", stderr="")
    return gh


def test_firmware_ids_come_from_firmware_and_recipe_paths_only():
    assert pending_prs.firmware_ids(["data/firmware/a/firmware.md", "data/firmware/a/signals.json",
                                     "data/recipes/m5stick-c__b/recipe.md", "data/boards/c/board.md",
                                     "jr/proposed_ledger.json", "docs/telemetry/x.md"]) == {"a", "b"}


def test_an_open_tick_pr_holds_every_firmware_its_files_name():
    idx = pending_prs.build([OPEN], [], NOW)
    for fid in ("nightdriverstrip", "newtool"):
        hold = idx.hold(fid)
        assert hold and hold.state == pending_prs.OPEN and hold.pr_ref == "#1500"
        assert hold.reason == "already_proposed"
    assert idx.hold("marauder") is None
    assert len(idx) == 2


def test_a_human_branch_and_a_bookkeeping_only_pr_hold_nothing():
    human = _pr(1509, ["data/firmware/x/firmware.md"], branch="feat/popularity")
    books = _pr(1435, ["jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"])
    assert len(pending_prs.build([human, books], [], NOW)) == 0


def test_a_tick_pr_closed_unmerged_inside_the_veto_ttl_holds_its_firmware_as_vetoed():
    closed = _pr(1478, NEWTOOL_PR_FILES, closedAt=_iso(NOW - timedelta(days=29)), mergedAt=None)
    hold = pending_prs.build([], [closed], NOW).hold("newtool")
    assert hold and hold.state == pending_prs.VETOED and hold.pr_ref == "#1478" and hold.reason == "vetoed"
    assert "closed unmerged" in hold.note


def test_a_veto_lapses_after_the_ttl_and_a_merged_pr_is_never_a_veto():
    old = _pr(1100, NEWTOOL_PR_FILES,
              closedAt=_iso(NOW - timedelta(days=pending_prs.VETO_TTL_DAYS, seconds=1)), mergedAt=None)
    merged = _pr(1496, ["data/firmware/squachwatch-cyd/signals.json"],
                 closedAt=_iso(NOW - timedelta(hours=1)), mergedAt=_iso(NOW - timedelta(hours=1)))
    undated = _pr(1101, ["data/recipes/m5cardputer__other/recipe.md"], mergedAt=None)
    assert len(pending_prs.build([], [old, merged, undated], NOW)) == 0


def test_an_open_pr_wins_over_an_older_veto_of_the_same_firmware():
    closed = _pr(1478, NEWTOOL_PR_FILES, closedAt=_iso(NOW - timedelta(days=1)), mergedAt=None)
    hold = pending_prs.build([OPEN], [closed], NOW).hold("newtool")
    assert hold.state == pending_prs.OPEN and hold.pr_ref == "#1500"


def test_load_reads_closed_unmerged_tick_prs_with_one_read_only_call():
    calls = []
    closed = _pr(1478, NEWTOOL_PR_FILES, closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None)
    idx = pending_prs.load(_gh([closed], calls=calls), [OPEN], NOW)
    assert idx.hold("newtool").state == pending_prs.OPEN and idx.hold("nightdriverstrip")
    assert len(calls) == 1
    argv = calls[0]
    assert argv[:4] == ("pr", "list", "--state", "closed")
    assert "files" in argv[argv.index("--json") + 1]
    search = argv[argv.index("--search") + 1]
    assert "is:unmerged" in search and f"closed:>={(NOW - timedelta(days=pending_prs.VETO_TTL_DAYS)).date()}" in search


def test_load_fails_closed_when_github_is_unreadable():
    assert pending_prs.load(_gh(rc=1), [OPEN], NOW) is None
    bad = lambda *a: SimpleNamespace(returncode=0, stdout="{not json", stderr="")   # noqa: E731
    assert pending_prs.load(bad, [OPEN], NOW) is None


def test_of_reads_the_context_index_and_defaults_to_empty():
    idx = pending_prs.build([OPEN], [], NOW)
    assert pending_prs.of(SimpleNamespace(pending=idx)) is idx
    assert len(pending_prs.of(SimpleNamespace())) == 0


def test_a_closed_pr_that_only_refreshed_a_record_vetoes_nothing_an_open_one_still_holds_it():
    """A veto rejects what a PR PROPOSED: recipes (every new firmware ships one) or mapped signals. A
    closed PR that only rewrote a catalogued record's firmware.md (popularity refresh) proposed nothing
    for it; an OPEN one still holds it, since a second edit of the same file would conflict."""
    closed = _pr(1511, ["data/firmware/atom-watch/firmware.md", "data/firmware/nightdriverstrip/firmware.md",
                        "data/firmware/nightdriverstrip/signals.json", "data/firmware/newtool/firmware.md",
                        "data/recipes/m5cardputer__newtool/recipe.md"],
                 closedAt=_iso(NOW - timedelta(days=1)), mergedAt=None)
    idx = pending_prs.build([], [closed], NOW)
    assert idx.hold("atom-watch") is None
    assert idx.hold("nightdriverstrip").state == idx.hold("newtool").state == pending_prs.VETOED
    opened = _pr(1512, ["data/firmware/atom-watch/firmware.md"])
    assert pending_prs.build([opened], [], NOW).hold("atom-watch").state == pending_prs.OPEN


def test_a_closed_list_cut_at_its_limit_is_flagged_truncated(monkeypatch):
    monkeypatch.setattr(pending_prs, "CLOSED_PR_LIMIT", 1)
    closed = _pr(1478, NEWTOOL_PR_FILES, closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None)
    assert pending_prs.load(_gh([closed]), [], NOW).truncated
    assert not pending_prs.load(_gh([]), [], NOW).truncated
