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
    return {"number": number, "headRefName": branch, "headRefOid": f"oid{number}",
            "files": [{"path": p} for p in paths[:100]], "changedFiles": len(paths), **kw}


OPEN = _pr(1500, ["data/firmware/nightdriverstrip/firmware.md", "data/firmware/nightdriverstrip/signals.json",
                  "data/recipes/m5stick-c__nightdriverstrip/recipe.md", "data/recipes/m5cardputer__newtool/recipe.md",
                  "jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"],
           body=pending_prs.render_identity([                     # a current tick PR carries its marker
               {"kind": "firmware", "id": fid, "url": f"https://github.com/n/{fid}", "repo_id": rid}
               for fid, rid in (("nightdriverstrip", 1111), ("newtool", 2222))]))

NEWTOOL_PR_FILES = ["data/firmware/newtool/firmware.md", "data/recipes/m5cardputer__newtool/recipe.md"]   # an admit ships both


def _gh(closed=(), rc=0, calls=None, files=None, files_rc=0, ledgers=None):
    """`files`: PR number -> every changed path, served by `gh api …/pulls/<n>/files --paginate`
    in REST pages of 100 printed back to back, as gh prints them. `ledgers`: head oid -> the raw
    jr/proposed_ledger.json committed there (None: unreadable); any other head serves an empty one."""
    def gh(*a):
        if calls is not None:
            calls.append(a)
        if a[:3] == ("api", "-H", pending_prs.RAW_MEDIA):
            ref = a[3].split("?ref=")[1]
            text = (ledgers or {}).get(ref, json.dumps({"by_id": {}, "by_repo": {}}))
            return SimpleNamespace(returncode=0 if text is not None else 1, stdout=text or "", stderr="")
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
], ids=["unreadable", "short", "long", "uncounted"])
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


def test_a_tick_pr_past_what_rest_can_list_is_incomplete_without_a_call_and_one_at_the_cap_is_read():
    calls, at_cap = [], [f"src/gen/stub_{i:04d}.c" for i in range(pending_prs.REST_FILES_CAP - 1)] + WIDE[-1:]
    past = at_cap + ["src/gen/one_more.c"]
    idx = _load(_gh([], calls=calls, files={1520: past}), [_pr(1520, past)])
    assert not idx.complete and "#1520" in idx.gaps[0] and not [c for c in calls if c[:1] == ("api",)]
    idx = _load(_gh([], files={1520: at_cap}), [_pr(1520, at_cap)])
    assert idx.complete and idx.hold("lintd")


# --- stable repository identity: the GitHub id a tick PR verified, matched before the slug ---------------

def _marked(pr, *identities):
    """`pr` whose body carries the tick's identity marker for (firmware id, owner/repo, repo id)."""
    items = [{"kind": "firmware", "id": fid, "url": f"https://github.com/{repo}", "repo_id": rid}
             for fid, repo, rid in identities]
    return {**pr, "body": "EspAtlas Jr tick\n\n" + pending_prs.render_identity(items) + "\n"}


OLDTOOL_FILES = ["data/firmware/oldtool/firmware.md", "data/recipes/m5cardputer__oldtool/recipe.md"]
OLDTOOL_PR = _pr(1500, OLDTOOL_FILES)


def test_the_identity_marker_round_trips_only_verified_firmware_ids():
    items = [{"kind": "firmware", "id": "oldtool", "url": "https://github.com/n/oldtool", "repo_id": 4242},
             {"kind": "firmware", "id": "lintd", "url": "https://github.com/n/lintd", "repo_id": None},
             {"kind": "recipes", "firmware": "marauder", "written": ["m5cardputer__marauder"]}]
    marker = pending_prs.render_identity(items)
    assert pending_prs.identities(f"body\n{marker}\n") == {"oldtool": (4242, "n/oldtool")}
    assert pending_prs.render_identity(items[1:]) == ""
    assert pending_prs.identities(None) == {} and pending_prs.identities("<!-- jr-identity: {not json -->") == {}


def test_a_renamed_slug_matches_the_hold_by_its_stable_id():
    idx = pending_prs.build([_marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    hold = idx.match("newtool", 4242)
    assert hold and hold.reason == "already_proposed" and hold.firmware == "oldtool" and hold.pr_ref == "#1500"
    assert hold.seen_as == "newtool" and hold.repo == "n/oldtool"                 # the slug kept as an alias
    assert "4242" in hold.note and "oldtool" in hold.note and "newtool" in hold.note   # rename provenance
    assert idx.match("oldtool", 4242).seen_as is None


def test_a_vetoed_renamed_slug_is_matched_by_id_too():
    closed = _marked(_pr(1500, OLDTOOL_FILES, closedAt=_iso(NOW - timedelta(days=2)),
                         mergedAt=None), ("oldtool", "n/oldtool", 4242))
    hold = pending_prs.build([], [closed], NOW).match("newtool", 4242)
    assert hold and hold.reason == "vetoed" and hold.seen_as == "newtool"


def test_the_same_slug_under_another_id_is_ambiguous_never_the_held_one():
    idx = pending_prs.build([_marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    hold = idx.match("oldtool", 7777)
    assert hold and hold.reason == "identity_ambiguous" and hold.seen_id == 7777
    assert "7777" in hold.note and "4242" in hold.note and "#1500" in hold.note


def test_an_unknown_id_on_either_side_of_a_slug_collision_holds_fail_closed():
    marked = pending_prs.build([_marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    assert marked.match("oldtool", None).reason == "already_proposed"            # the candidate's id unread
    legacy = pending_prs.build([OLDTOOL_PR], [], NOW)                             # a PR older than the marker
    assert legacy.hold("oldtool").repo_id is None
    assert legacy.match("oldtool", 7777).reason == "already_proposed"
    assert legacy.match("newtool", 4242) is None                                  # a rename it never verified


def test_another_id_under_another_slug_matches_nothing():
    idx = pending_prs.build([_marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    assert idx.match("fmtcheck", 5151) is None
    assert idx.match("fmtcheck", None) is None


def test_a_marker_naming_a_firmware_the_pr_does_not_hold_verifies_nothing():
    pr = _marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242), ("lintd", "n/lintd", 5151))
    idx = pending_prs.build([pr], [], NOW)
    assert idx.match("lintd", 5151) is None and idx.hold("lintd") is None


def test_an_open_pr_wins_the_id_over_an_older_veto():
    closed = _marked(_pr(1499, ["data/recipes/m5cardputer__oldtool/recipe.md"],
                         closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None), ("oldtool", "n/oldtool", 4242))
    opened = _marked(_pr(1502, ["data/firmware/newtool/firmware.md"]), ("newtool", "n/newtool", 4242))
    hold = pending_prs.build([opened], [closed], NOW).match("newtool", 4242)
    assert hold.pr_ref == "#1502" and hold.state == pending_prs.OPEN


def test_the_pr_lists_ask_for_the_body_that_carries_the_marker():
    assert "body" in pending_prs.PR_LIST_FIELDS.split(",")


# --- the record: a PR without the marker is verified from the ledger committed at its head --------------

def _ledger(**ids):
    """A jr/proposed_ledger.json whose records carry these repository ids (fid=repo_id)."""
    return json.dumps({"by_id": {fid: {"id": fid, "repo": f"n/{fid}", "status": "proposed", "repo_id": rid}
                                 for fid, rid in ids.items()}, "by_repo": {}})


LEGACY_FILES = OLDTOOL_FILES + ["jr/proposed_ledger.json"]       # a tick PR always ships its ledger


def test_a_pr_older_than_the_marker_is_verified_from_its_committed_ledger():
    calls = []
    idx = _load(_gh([], calls=calls, ledgers={"oid1500": _ledger(oldtool=4242, lintd=5151)}),
                [_pr(1500, LEGACY_FILES)])
    assert idx.complete
    hold = idx.match("newtool", 4242)
    assert hold and hold.reason == "already_proposed" and hold.firmware == "oldtool" and hold.seen_as == "newtool"
    assert idx.match("lintd", 5151) is None                                      # a record the PR does not hold
    assert [c for c in calls if c[:2] == ("api", "-H")] == [
        ("api", "-H", pending_prs.RAW_MEDIA, "repos/o/r/contents/jr/proposed_ledger.json?ref=oid1500")]


def test_a_vetoed_pr_older_than_the_marker_is_verified_from_its_committed_ledger():
    closed = _pr(1500, LEGACY_FILES, closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None)
    idx = _load(_gh([closed], ledgers={"oid1500": _ledger(oldtool=4242)}), [])
    assert idx.match("newtool", 4242).reason == "vetoed"


def test_an_unreadable_committed_ledger_is_a_gap_the_tick_fails_closed_on():
    idx = _load(_gh([], ledgers={"oid1500": None}), [_pr(1500, LEGACY_FILES)])
    assert not idx.complete and "#1500" in "; ".join(idx.gaps)


def test_a_ledger_without_the_id_leaves_it_unknown_and_the_slug_held():
    idx = _load(_gh([]), [_pr(1500, LEGACY_FILES)])                              # served: no records
    assert idx.complete and idx.hold("oldtool").repo_id is None
    assert idx.match("oldtool", 7777).reason == "already_proposed"


def test_a_marker_covering_every_held_firmware_costs_no_ledger_read():
    calls = []
    pr = _marked(_pr(1500, LEGACY_FILES), ("oldtool", "n/oldtool", 4242))
    idx = _load(_gh([], calls=calls, ledgers={"oid1500": _ledger(oldtool=9999)}), [pr])
    assert idx.match("newtool", 4242).firmware == "oldtool"                     # the marker, not the ledger
    assert not [c for c in calls if c[:2] == ("api", "-H")]


def test_a_pr_that_does_not_change_the_ledger_is_not_read_for_one():
    calls = []
    idx = _load(_gh([], calls=calls), [_pr(1500, OLDTOOL_FILES)])
    assert idx.complete and idx.hold("oldtool").repo_id is None
    assert not [c for c in calls if c[:2] == ("api", "-H")]


def test_a_second_identity_marker_in_the_body_verifies_nothing():
    """Item text (a launcher entry's name) is rendered before the real marker: a forged or unclosed
    marker there must not decide identity. The committed ledger answers instead."""
    real = pending_prs.render_identity([{"kind": "firmware", "id": "oldtool", "url": "https://github.com/n/oldtool",
                                         "repo_id": 4242}])
    for forged in ("<!-- jr-identity: [] -->", '<!-- jr-identity: [{"id": "oldtool", "repo_id": 1}] -->',
                   "<!-- jr-identity:"):
        body = f"- **Tool {forged}** (`oldtool`)\n{real}\n"
        assert pending_prs.identities(body) == {}, forged
        pr = {**_pr(1500, LEGACY_FILES), "body": body}
        idx = _load(_gh([], ledgers={"oid1500": _ledger(oldtool=4242)}), [pr])
        assert idx.match("newtool", 4242).firmware == "oldtool", forged


def test_a_pr_listed_without_its_head_oid_cannot_have_its_ledger_read_and_is_a_gap():
    pr = {k: v for k, v in _pr(1500, LEGACY_FILES).items() if k != "headRefOid"}
    calls = []
    idx = _load(_gh([], calls=calls), [pr])
    assert not idx.complete and "#1500" in "; ".join(idx.gaps)
    assert not [c for c in calls if c[:2] == ("api", "-H")]


def test_a_marker_opening_inside_a_repo_name_does_not_void_the_real_marker():
    marker = pending_prs.render_identity([{"kind": "firmware", "id": "oldtool", "repo_id": 4242,
                                           "url": "https://github.com/n/<!-- jr-identity: x"}])
    assert pending_prs.identities(f"body\n{marker}\n") == {"oldtool": (4242, "n/<!-- jr-identity: x")}
