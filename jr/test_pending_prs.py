"""Tests for jr/pending_prs.py — what Jr's own tick PRs already hold, read from GitHub's file lists.

Fake gh only: every answer is scripted. Run: cd jr && python3 -m pytest test_pending_prs.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import pending_prs

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _pr(number, paths, branch="jr/tick-20261107-0300", **kw):
    """A PR as `gh pr list --json …,files,changedFiles` lists it: at most the first 100 files."""
    return {"number": number, "headRefName": branch, "files": [{"path": p} for p in paths[:100]],
            "changedFiles": len(paths), **kw}


OPEN = _pr(1500, ["data/firmware/nightdriverstrip/firmware.md", "data/firmware/nightdriverstrip/signals.json",
                  "data/recipes/m5stick-c__nightdriverstrip/recipe.md", "data/recipes/m5cardputer__newtool/recipe.md",
                  "jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"])

NEWTOOL_PR_FILES = ["data/firmware/newtool/firmware.md", "data/recipes/m5cardputer__newtool/recipe.md"]   # an admit ships both


def _gh(closed=(), rc=0, calls=None, files=None, files_rc=0):
    """`files`: PR number -> every changed path, served by `gh api …/pulls/<n>/files --paginate`
    in REST pages of 100 printed back to back, as gh prints them."""
    def gh(*a):
        if calls is not None:
            calls.append(a)
        if a[:1] == ("api",):
            number = int(a[1].split("/pulls/")[1].split("/")[0])
            paths = (files or {}).get(number, [])
            pages = "".join(json.dumps([{"filename": p} for p in paths[i:i + 100]])
                            for i in range(0, max(len(paths), 1), 100))
            return SimpleNamespace(returncode=files_rc, stdout=pages if files_rc == 0 else "", stderr="")
        return SimpleNamespace(returncode=rc, stdout=json.dumps(list(closed)) if rc == 0 else "", stderr="")
    return gh


SLUG = "o/r"
PADDING = [f"src/parser/rule_{i:03d}.c" for i in range(100)]          # 100 files GitHub lists first
WIDE = PADDING + ["data/recipes/m5cardputer__lintd/recipe.md"]        # the 101st names the firmware


def _load(gh, open_prs, open_limit=500):
    return pending_prs.load(gh, open_prs, NOW, slug=SLUG, open_limit=open_limit)


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
    idx = _load(_gh([closed], calls=calls), [OPEN])
    assert idx.hold("newtool").state == pending_prs.OPEN and idx.hold("nightdriverstrip")
    assert len(calls) == 1
    argv = calls[0]
    assert argv[:4] == ("pr", "list", "--state", "closed")
    assert {"files", "changedFiles"} <= set(argv[argv.index("--json") + 1].split(","))
    search = argv[argv.index("--search") + 1]
    assert "is:unmerged" in search and f"closed:>={(NOW - timedelta(days=pending_prs.VETO_TTL_DAYS)).date()}" in search


def test_load_fails_closed_when_github_is_unreadable():
    assert _load(_gh(rc=1), [OPEN]) is None
    bad = lambda *a: SimpleNamespace(returncode=0, stdout="{not json", stderr="")   # noqa: E731
    assert _load(bad, [OPEN]) is None


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


def test_a_closed_list_cut_at_its_limit_is_incomplete(monkeypatch):
    monkeypatch.setattr(pending_prs, "CLOSED_PR_LIMIT", 1)
    closed = _pr(1478, NEWTOOL_PR_FILES, closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None)
    cut = _load(_gh([closed]), [])
    assert not cut.complete and "closed" in cut.gaps[0] and "1" in cut.gaps[0]
    assert _load(_gh([]), []).complete


def test_an_open_list_cut_at_its_limit_is_incomplete_even_when_it_shows_no_tick_pr():
    human = _pr(1509, ["src/lexer/tokens.c"], branch="feat/lexer")
    cut = _load(_gh([]), [human], open_limit=1)
    assert not cut.complete and "open" in cut.gaps[0]
    assert _load(_gh([]), [human], open_limit=2).complete


def test_a_101_file_open_tick_pr_is_read_whole_and_holds_the_firmware_its_101st_file_names():
    calls = []
    wide = _pr(1520, WIDE)
    assert len(wide["files"]) == 100 and wide["changedFiles"] == 101          # what gh pr list shows
    idx = _load(_gh([], calls=calls, files={1520: WIDE}), [wide])
    assert idx.complete, idx.gaps
    assert idx.hold("lintd").state == pending_prs.OPEN and idx.hold("lintd").pr_ref == "#1520"
    api = [c for c in calls if c[:1] == ("api",)]
    assert api == [("api", f"repos/{SLUG}/pulls/1520/files?per_page=100", "--paginate")]


def test_a_101_file_vetoed_tick_pr_is_read_whole_and_vetoes_the_firmware_its_101st_file_names():
    wide = _pr(1478, WIDE, closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None)
    idx = _load(_gh([wide], files={1478: WIDE}), [])
    assert idx.complete, idx.gaps
    assert idx.hold("lintd").state == pending_prs.VETOED


def test_a_100_file_tick_pr_is_already_whole_and_costs_no_extra_call():
    calls = []
    full = _pr(1520, PADDING[:99] + ["data/recipes/m5cardputer__lintd/recipe.md"])
    idx = _load(_gh([], calls=calls), [full])
    assert idx.complete and idx.hold("lintd")
    assert not [c for c in calls if c[:1] == ("api",)]


def test_a_cut_file_list_of_a_human_pr_or_a_lapsed_veto_needs_no_extra_call():
    calls = []
    human = _pr(1509, WIDE, branch="feat/lexer")
    lapsed = _pr(1100, WIDE, closedAt=_iso(NOW - timedelta(days=pending_prs.VETO_TTL_DAYS + 1)), mergedAt=None)
    idx = _load(_gh([lapsed], calls=calls), [human])
    assert idx.complete and len(idx) == 0
    assert not [c for c in calls if c[:1] == ("api",)]


@pytest.mark.parametrize("pr, served, files_rc", [
    (_pr(1520, WIDE), {1520: WIDE}, 1),                                   # the file listing fails
    (_pr(1520, WIDE), {1520: WIDE[:100]}, 0),                             # still one file short
    (_pr(1520, WIDE), {1520: WIDE + ["src/extra.c"]}, 0),                 # more than it counted
    ({**_pr(1520, WIDE[:5]), "changedFiles": None}, {1520: WIDE[:5]}, 0),  # no count to check against
    ({**_pr(1520, WIDE), "changedFiles": 3001}, {}, 0),                   # past what REST can list
], ids=["unreadable", "short", "long", "uncounted", "past-rest-cap"])
def test_a_tick_pr_whose_files_cannot_be_shown_whole_leaves_the_index_incomplete(pr, served, files_rc):
    idx = _load(_gh([], files=served, files_rc=files_rc), [pr])
    assert not idx.complete and "#1520" in idx.gaps[0]


def test_a_cut_file_list_without_a_repo_slug_is_incomplete():
    idx = pending_prs.load(_gh([], files={1520: WIDE}), [_pr(1520, WIDE)], NOW, slug="", open_limit=500)
    assert not idx.complete and "#1520" in idx.gaps[0]


@pytest.mark.parametrize("stdout", ["", "  \n", "[{\"filename\": \"a.c\"}] {not json", "{\"filename\": \"a.c\"}",
                                    "[{\"name\": \"a.c\"}]"], ids=["empty", "blank", "bad-json", "object", "no-filename"])
def test_an_unreadable_rest_file_listing_leaves_the_index_incomplete(stdout):
    def gh(*a):
        if a[:1] == ("api",):
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")
    assert not _load(gh, [_pr(1520, WIDE)]).complete


def test_rest_pages_separated_by_whitespace_are_read_as_one_listing():
    pages = json.dumps([{"filename": p} for p in WIDE[:100]]) + "\n" + json.dumps([{"filename": WIDE[100]}]) + "\n"
    gh = lambda *a: SimpleNamespace(returncode=0, stdout=pages if a[:1] == ("api",) else "[]", stderr="")  # noqa: E731
    assert _load(gh, [_pr(1520, WIDE)]).hold("lintd")
