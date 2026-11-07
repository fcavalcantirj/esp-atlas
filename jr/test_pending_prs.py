"""Tests for jr/pending_prs.py — what Jr's own tick PRs already hold, read from GitHub's file lists.

Fake gh only: every answer is scripted. Run: cd jr && python3 -m pytest test_pending_prs.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import pending_prs
import publish

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _pr(number, paths, branch="jr/tick-20261107-0300", **kw):
    """A PR as `gh pr list --json …,files,changedFiles` lists it: at most the first 100 files. Opened
    by the Jr bot from a branch of the base repository unless `kw` says otherwise."""
    return {"number": number, "headRefName": branch, "headRefOid": f"oid{number}",
            "author": {"login": publish.JR_LOGIN}, "isCrossRepository": False,
            "files": [{"path": p} for p in paths[:100]], "changedFiles": len(paths), **kw}


OPEN = _pr(1500, ["data/firmware/nightdriverstrip/firmware.md", "data/firmware/nightdriverstrip/signals.json",
                  "data/recipes/m5stick-c__nightdriverstrip/recipe.md", "data/recipes/m5cardputer__newtool/recipe.md",
                  "jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"],
           body=pending_prs.render_identity([                     # a current tick PR carries its marker
               {"kind": "firmware", "id": fid, "url": f"https://github.com/n/{fid}", "repo_id": rid}
               for fid, rid in (("nightdriverstrip", 1111), ("newtool", 2222))]))

NEWTOOL_PR_FILES = ["data/firmware/newtool/firmware.md", "data/recipes/m5cardputer__newtool/recipe.md"]   # an admit ships both


def _ledger_repos(ledgers) -> dict:
    """owner/repo -> repository id, as every served ledger records it: GitHub agrees by default."""
    out = {}
    for text in (ledgers or {}).values():
        for rec in (json.loads(text).get("by_id") or {}).values() if text else ():
            if isinstance(rec.get("repo"), str) and type(rec.get("repo_id")) is int:
                out[rec["repo"]] = rec["repo_id"]
    return out


def _number_in(route: str) -> int:
    return int(route.split("/pulls/")[1].split("/")[0])


def _gh(closed=(), rc=0, calls=None, files=None, files_rc=0, ledgers=None, repos=None, pages=None, heads=None,
        counts=None):
    """`files`: PR number -> every changed path, served by `gh api …/pulls/<n>/files --paginate`
    in REST pages of 100 printed back to back, as gh prints them (`pages`: PR number -> the pages served
    instead, as a PR edited mid-listing serves them). `gh api …/pulls/<n>` answers head sha `oid<n>`
    (`heads`: PR number -> the shas successive reads answer) and changed_files len(files) (`counts`
    overrides). `ledgers`: head oid -> the raw jr/proposed_ledger.json committed there (None: unreadable); any other head serves an empty one.
    `repos`: owner/repo -> the id `gh api repos/<owner/repo>` answers (redirects followed; None or
    absent: the call fails); by default the ids the served ledgers record."""
    repos = _ledger_repos(ledgers) if repos is None else repos

    def gh(*a):
        if calls is not None:
            calls.append(a)
        if a[:1] == ("api",) and len(a) == 2 and a[1].count("/") == 2 and "/pulls/" not in a[1]:
            rid = repos.get(a[1].removeprefix("repos/"))
            return SimpleNamespace(returncode=0 if rid is not None else 1, stderr="" if rid else "HTTP 404",
                                   stdout=json.dumps({"id": rid, "full_name": a[1][6:]}) if rid is not None else "")
        if a[:3] == ("api", "-H", pending_prs.RAW_MEDIA):
            ref = a[3].split("?ref=")[1]
            text = (ledgers or {}).get(ref, json.dumps({"by_id": {}, "by_repo": {}}))
            return SimpleNamespace(returncode=0 if text is not None else 1, stdout=text or "", stderr="")
        if a[:1] == ("api",) and a[1].split("/pulls/")[1].isdigit():
            number = int(a[1].split("/pulls/")[1])
            shas = (heads or {}).get(number) or [f"oid{number}"]
            sha = shas.pop(0) if len(shas) > 1 else shas[0]
            count = (counts or {}).get(number, len((files or {}).get(number, [])))
            return SimpleNamespace(returncode=0, stdout=json.dumps({"head": {"sha": sha}, "changed_files": count}),
                                   stderr="")
        if a[:1] == ("api",) and _number_in(a[1]) in (pages or {}):
            served = "".join(json.dumps([{"filename": p} for p in page]) for page in pages[_number_in(a[1])])
            return SimpleNamespace(returncode=0, stdout=served, stderr="")
        if a[:1] == ("api",):
            number = _number_in(a[1])
            paths = (files or {}).get(number, [])
            served = "".join(json.dumps([{"filename": p} for p in paths[i:i + 100]])
                             for i in range(0, max(len(paths), 1), 100))
            return SimpleNamespace(returncode=files_rc, stdout=served if files_rc == 0 else "", stderr="")
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
    assert len([c for c in calls if c[:1] == ("pr",)]) == 1                      # + OPEN's committed ledger, read raw
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


def test_a_listing_edited_between_pages_that_repeats_one_path_and_drops_the_held_one_is_incomplete():
    shifted = [WIDE[:100], WIDE[99:100]]           # an edit mid-listing: page 2 restarts one row early
    gh = _gh([], files={1520: WIDE}, pages={1520: shifted})
    idx = _load(gh, [_pr(1520, WIDE)])             # 101 rows, as counted — but 100 paths, lintd's missing
    assert not idx.complete and "#1520" in idx.gaps[0]


def test_a_head_that_moves_while_the_pages_are_read_leaves_the_index_incomplete():
    gh = _gh([], files={1520: WIDE}, heads={1520: ["oid1520", "oid1520-pushed"]})
    idx = _load(gh, [_pr(1520, WIDE)])
    assert not idx.complete and "#1520" in idx.gaps[0]


@pytest.mark.parametrize("heads, counts", [
    ({1520: ["oid1520-stale", "oid1520-stale"]}, None),     # stable, but not the head the PR list showed
    (None, {1520: 102}),                                    # GitHub now counts another changed file
], ids=["not-the-listed-head", "count-mismatch"])
def test_pages_not_bound_to_the_listed_head_and_count_leave_the_index_incomplete(heads, counts):
    idx = _load(_gh([], files={1520: WIDE}, heads=heads, counts=counts), [_pr(1520, WIDE)])
    assert not idx.complete and "#1520" in idx.gaps[0]


def test_stable_pages_whose_unique_paths_number_changed_files_are_whole_bound_by_two_head_reads():
    calls = []
    idx = _load(_gh([], calls=calls, files={1520: WIDE}), [_pr(1520, WIDE)])
    assert idx.complete, idx.gaps
    assert idx.hold("lintd").state == pending_prs.OPEN
    head = ("api", f"repos/{SLUG}/pulls/1520")
    assert [c for c in calls if c[:1] == ("api",)] == [
        head, ("api", f"repos/{SLUG}/pulls/1520/files?per_page=100", "--paginate"), head]


# --- stable repository identity: the GitHub id a tick PR verified, matched before the slug ---------------

def _marked(pr, *identities):
    """`pr` whose body carries the tick's identity marker for (firmware id, owner/repo, repo id)."""
    items = [{"kind": "firmware", "id": fid, "url": f"https://github.com/{repo}", "repo_id": rid}
             for fid, repo, rid in identities]
    return {**pr, "body": "EspAtlas Jr tick\n\n" + pending_prs.render_identity(items) + "\n"}


def _verified(pr, *identities):
    """`pr` marked for (firmware id, owner/repo, repo id) AND verified so by load() — the ids its
    committed ledger confirmed. build() accepts no other repository id."""
    return {**_marked(pr, *identities), "_identities": {fid: (rid, repo) for fid, repo, rid in identities}}


OLDTOOL_FILES = ["data/firmware/oldtool/firmware.md", "data/recipes/m5cardputer__oldtool/recipe.md"]
OLDTOOL_PR = _pr(1500, OLDTOOL_FILES)


def test_the_identity_marker_round_trips_only_verified_firmware_ids():
    items = [{"kind": "firmware", "id": "oldtool", "url": "https://github.com/n/oldtool", "repo_id": 4242},
             {"kind": "firmware", "id": "lintd", "url": "https://github.com/n/lintd", "repo_id": None},
             {"kind": "recipes", "firmware": "marauder", "written": ["m5cardputer__marauder"]}]
    marker = pending_prs.render_identity(items)
    assert pending_prs.identities(f"body\n{marker}\n") == {"oldtool": (4242, "n/oldtool")}
    assert pending_prs.render_identity(items[1:]) == ""
    assert pending_prs.identities(None) == {} and pending_prs.identities("no marker") == {}
    assert pending_prs.identities("<!-- jr-identity: {not json -->") is None      # unreadable: ambiguous


def test_a_renamed_slug_matches_the_hold_by_its_stable_id():
    idx = pending_prs.build([_verified(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    hold = idx.match("newtool", 4242)
    assert hold and hold.reason == "already_proposed" and hold.firmware == "oldtool" and hold.pr_ref == "#1500"
    assert hold.seen_as == "newtool" and hold.repo == "n/oldtool"                 # the slug kept as an alias
    assert "4242" in hold.note and "oldtool" in hold.note and "newtool" in hold.note   # rename provenance
    assert idx.match("oldtool", 4242).seen_as is None


def test_a_vetoed_renamed_slug_is_matched_by_id_too():
    closed = _verified(_pr(1500, OLDTOOL_FILES, closedAt=_iso(NOW - timedelta(days=2)),
                         mergedAt=None), ("oldtool", "n/oldtool", 4242))
    hold = pending_prs.build([], [closed], NOW).match("newtool", 4242)
    assert hold and hold.reason == "vetoed" and hold.seen_as == "newtool"


def test_the_same_slug_under_another_id_is_ambiguous_never_the_held_one():
    idx = pending_prs.build([_verified(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    hold = idx.match("oldtool", 7777)
    assert hold and hold.reason == "identity_ambiguous" and hold.seen_id == 7777
    assert "7777" in hold.note and "4242" in hold.note and "#1500" in hold.note


def test_an_unknown_id_on_either_side_of_a_slug_collision_holds_fail_closed():
    marked = pending_prs.build([_verified(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    assert marked.match("oldtool", None).reason == "already_proposed"            # the candidate's id unread
    legacy = pending_prs.build([OLDTOOL_PR], [], NOW)                             # a PR older than the marker
    assert legacy.hold("oldtool").repo_id is None
    assert legacy.match("oldtool", 7777).reason == "already_proposed"
    assert legacy.match("newtool", 4242) is None                                  # a rename it never verified


def test_another_id_under_another_slug_matches_nothing():
    idx = pending_prs.build([_verified(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    assert idx.match("fmtcheck", 5151) is None
    assert idx.match("fmtcheck", None) is None


def test_a_marker_naming_a_firmware_the_pr_does_not_hold_verifies_nothing():
    pr = _marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242), ("lintd", "n/lintd", 5151))
    idx = pending_prs.build([pr], [], NOW)
    assert idx.match("lintd", 5151) is None and idx.hold("lintd") is None


def test_an_open_pr_wins_the_id_over_an_older_veto():
    closed = _verified(_pr(1499, ["data/recipes/m5cardputer__oldtool/recipe.md"],
                         closedAt=_iso(NOW - timedelta(days=2)), mergedAt=None), ("oldtool", "n/oldtool", 4242))
    opened = _verified(_pr(1502, ["data/firmware/newtool/firmware.md"]), ("newtool", "n/newtool", 4242))
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


def test_a_pr_that_does_not_change_the_ledger_is_not_read_for_one():
    calls = []
    idx = _load(_gh([], calls=calls), [_pr(1500, OLDTOOL_FILES)])
    assert idx.complete and idx.hold("oldtool").repo_id is None
    assert not [c for c in calls if c[:2] == ("api", "-H")]


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


# --- the marker is never trusted alone: the ledger committed at the PR's head decides (#986/#987) -------

def _closed(pr):
    return {**pr, "closedAt": _iso(NOW - timedelta(days=2)), "mergedAt": None}


def _index_of(pr, vetoed, ledgers, calls=None, repos=None):
    """load() over `pr`, listed open or closed unmerged inside the veto TTL."""
    gh = _gh([_closed(pr)] if vetoed else [], calls=calls, ledgers=ledgers, repos=repos)
    return _load(gh, []) if vetoed else _load(gh, [pr])


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_forged_marker_keeps_the_ledger_id_held_and_never_holds_the_claimed_one(vetoed):
    """The body of PR #1500 was edited: its marker claims oldtool is repository 7777, the ledger it
    committed says 4242. 4242 stays held (renamed or not); unrelated 7777 is neither held nor vetoed."""
    pr = _marked(_pr(1500, LEGACY_FILES), ("oldtool", "n/oldtool", 7777))
    idx = _index_of(pr, vetoed, {"oid1500": _ledger(oldtool=4242)})
    assert idx.complete
    assert idx.hold("oldtool").repo_id == 4242
    assert idx.match("newtool", 4242).firmware == "oldtool"                       # the rename still caught
    assert idx.match("unrelated", 7777) is None                                   # 7777 never held or vetoed
    assert 7777 not in idx.by_repo_id


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_marker_its_committed_ledger_agrees_with_still_covers_the_rename(vetoed):
    calls = []
    pr = _marked(_pr(1500, LEGACY_FILES), ("oldtool", "n/oldtool", 4242))
    idx = _index_of(pr, vetoed, {"oid1500": _ledger(oldtool=4242)}, calls)
    assert idx.complete
    hold = idx.match("newtool", 4242)
    assert hold.firmware == "oldtool" and hold.seen_as == "newtool"
    assert hold.reason == ("vetoed" if vetoed else "already_proposed")
    assert [c[3] for c in calls if c[:2] == ("api", "-H")] == ["repos/o/r/contents/jr/proposed_ledger.json?ref=oid1500"]


@pytest.mark.parametrize("ledger", [_ledger(), json.dumps({"by_id": {"oldtool": {"id": "oldtool", "repo": "n/oldtool",
                                                                                  "status": "proposed"}}, "by_repo": {}})],
                         ids=["no-record", "record-without-id"])
def test_a_marker_its_committed_ledger_does_not_confirm_verifies_nothing(ledger):
    pr = _marked(_pr(1500, LEGACY_FILES), ("oldtool", "n/oldtool", 4242))
    idx = _load(_gh([], ledgers={"oid1500": ledger}), [pr])
    assert idx.complete and idx.hold("oldtool").repo_id is None and not idx.by_repo_id
    assert idx.match("newtool", 4242) is None                                     # a rename it never verified
    assert idx.match("oldtool", 7777).reason == "already_proposed"                # the slug still holds


def test_a_marked_pr_that_does_not_change_the_ledger_verifies_nothing():
    pr = _marked(_pr(1500, OLDTOOL_FILES), ("oldtool", "n/oldtool", 4242))
    idx = _load(_gh([]), [pr])
    assert idx.complete and idx.hold("oldtool").repo_id is None and not idx.by_repo_id


def test_build_alone_never_trusts_a_body_marker():
    idx = pending_prs.build([_marked(OLDTOOL_PR, ("oldtool", "n/oldtool", 4242))], [], NOW)
    assert idx.hold("oldtool").repo_id is None and idx.match("newtool", 4242) is None


REAL_MARKER = pending_prs.render_identity([{"kind": "firmware", "id": "oldtool", "url": "https://github.com/n/oldtool",
                                            "repo_id": 4242}])
AMBIGUOUS_BODIES = {
    "second-marker": f"- **Tool <!-- jr-identity: [] -->** (`oldtool`)\n{REAL_MARKER}\n",
    "forged-second": f'- **Tool <!-- jr-identity: [{{"id": "oldtool", "repo_id": 1}}] -->**\n{REAL_MARKER}\n',
    "unclosed-second": f"- **Tool <!-- jr-identity:** (`oldtool`)\n{REAL_MARKER}\n",
    "same-marker-twice": f"{REAL_MARKER}\n{REAL_MARKER}\n",
    "conflicting-ids": '<!-- jr-identity: [{"id": "oldtool", "repo_id": 4242}, {"id": "oldtool", "repo_id": 7777}] -->',
    "duplicate-entry": '<!-- jr-identity: [{"id": "oldtool", "repo_id": 4242}, {"id": "oldtool", "repo_id": 4242}] -->',
    "unreadable": "<!-- jr-identity: [{not json -->",
    "unclosed": '<!-- jr-identity: [{"id": "oldtool", "repo_id": 4242}]',
    "not-a-list": '<!-- jr-identity: {"oldtool": 4242} -->',
}


@pytest.mark.parametrize("body", AMBIGUOUS_BODIES.values(), ids=AMBIGUOUS_BODIES.keys())
def test_a_conflicting_duplicate_or_unreadable_marker_is_ambiguous(body):
    assert pending_prs.identities(body) is None


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
@pytest.mark.parametrize("body", AMBIGUOUS_BODIES.values(), ids=AMBIGUOUS_BODIES.keys())
def test_an_ambiguous_marker_leaves_the_index_incomplete_even_when_the_ledger_agrees(body, vetoed):
    pr = {**_pr(1500, LEGACY_FILES), "body": body}
    idx = _index_of(pr, vetoed, {"oid1500": _ledger(oldtool=4242)})
    assert not idx.complete
    assert any("#1500" in g and "identity marker" in g for g in idx.gaps), idx.gaps


def test_an_ambiguous_marker_on_a_pr_that_holds_nothing_is_no_gap():
    """A human branch, a lapsed veto or a merged PR holds nothing: its body decides nothing either."""
    body = AMBIGUOUS_BODIES["conflicting-ids"]
    human = {**_pr(1500, LEGACY_FILES, branch="feature/x"), "body": body}
    lapsed = {**_pr(1501, LEGACY_FILES), "body": body, "closedAt": _iso(NOW - timedelta(days=40)), "mergedAt": None}
    merged = {**_pr(1502, LEGACY_FILES), "body": body, "closedAt": _iso(NOW - timedelta(days=2)),
              "mergedAt": _iso(NOW - timedelta(days=2))}
    assert _load(_gh([lapsed, merged]), [human]).complete


LEGACY_GROWTH_FILES = ["data/firmware/cardskimmerdetector-m5cardputer/firmware.md",
                       "data/firmware/nightdriverstrip/firmware.md", "data/firmware/nightdriverstrip/signals.json",
                       "data/recipes/m5cardputer__cardskimmerdetector-m5cardputer/recipe.md",
                       "docs/telemetry/data-trend.jsonl", "jr/proposed_ledger.json"]


def test_a_legacy_markerless_growth_pr_resolves_ids_from_its_ledger_else_by_slug():
    """The shape of open growth PRs #1511/#1513: no marker, a committed ledger where one held firmware's
    record carries its repo_id and another's (an older merged record) does not."""
    led = json.dumps({"by_id": {
        "cardskimmerdetector-m5cardputer": {"id": "cardskimmerdetector-m5cardputer", "status": "merged",
                                            "repo": "Aat440hz/CardSkimmerDetector-M5Cardputer", "repo_id": 777925318},
        "nightdriverstrip": {"id": "nightdriverstrip", "status": "merged", "repo": "plummerssoftwarellc/nightdriverstrip"}},
        "by_repo": {}})
    pr = {**_pr(1513, LEGACY_GROWTH_FILES, branch="jr/tick-20261107-0400"), "body": "EspAtlas Jr tick\n\nno marker\n"}
    idx = _load(_gh([], ledgers={"oid1513": led}), [pr])
    assert idx.complete
    card = idx.hold("cardskimmerdetector-m5cardputer")
    assert card.repo_id == 777925318 and card.repo == "aat440hz/cardskimmerdetector-m5cardputer"
    assert idx.match("cardskimmer-renamed", 777925318).firmware == "cardskimmerdetector-m5cardputer"
    assert idx.hold("nightdriverstrip").repo_id is None
    assert idx.match("nightdriverstrip", 123).reason == "already_proposed"         # slug fallback holds


def test_an_ambiguous_marker_on_a_tick_pr_that_holds_nothing_is_no_gap():
    """A bookkeeping-only tick PR, or a closed one that only refreshed a record, holds nothing: an
    edited body there decides no identity, so it must not stall every tick."""
    body = AMBIGUOUS_BODIES["conflicting-ids"]
    bookkeeping = {**_pr(1500, ["jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl"]), "body": body}
    refresh = _closed({**_pr(1501, ["data/firmware/oldtool/firmware.md"]), "body": body})
    calls = []
    idx = _load(_gh([refresh], calls=calls), [bookkeeping])
    assert idx.complete and len(idx) == 0
    assert not [c for c in calls if c[:2] == ("api", "-H")]


# --- a committed ledger id is trusted only from the Jr bot's own same-repo PR, and only once GitHub's
#     repository metadata confirms it (#998/#1001): committed text can be altered by any later commit ---

NEWTOOL_LEDGER_FILES = NEWTOOL_PR_FILES + ["jr/proposed_ledger.json"]
NEWTOOL_META_CALL = ("api", "repos/n/newtool")


def _newtool_index(vetoed, ledger_id=4242, repos=None, calls=None, **kw):
    """load() over bot PR #1500 holding newtool, its committed ledger recording `ledger_id` for n/newtool."""
    return _index_of(_pr(1500, NEWTOOL_LEDGER_FILES, **kw), vetoed, {"oid1500": _ledger(newtool=ledger_id)},
                     calls, {"n/newtool": 4242} if repos is None else repos)


def _held_by_slug_only(idx, rid):
    assert idx.complete, idx.gaps                                                  # no new gap: just no id
    assert idx.hold("newtool").repo_id is None and not idx.by_repo_id
    assert idx.match("newtool", rid).reason in ("already_proposed", "vetoed")      # the slug still holds
    assert idx.match("renamedtool", rid) is None and idx.match("renamedtool", 4242) is None


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_bot_same_repo_ledger_id_github_confirms_is_accepted(vetoed):
    calls = []
    idx = _newtool_index(vetoed, calls=calls)
    assert idx.complete and idx.hold("newtool").repo_id == 4242 and set(idx.by_repo_id) == {4242}
    assert idx.match("renamedtool", 4242).firmware == "newtool"
    assert NEWTOOL_META_CALL in calls                                              # independently confirmed


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_id_altered_by_a_later_commit_is_rejected_and_the_slug_held(vetoed):
    """A later commit on the bot's own PR rewrote the ledger: newtool is 7777. GitHub says n/newtool is 4242."""
    idx = _newtool_index(vetoed, ledger_id=7777)
    _held_by_slug_only(idx, 7777)
    assert 7777 not in idx.by_repo_id and idx.match("unrelated", 7777) is None


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
@pytest.mark.parametrize("author", [{"login": "mallory"}, {}, None], ids=["foreign", "no-login", "no-author"])
def test_a_ledger_id_on_a_pr_not_authored_by_the_jr_bot_is_never_accepted(vetoed, author):
    _held_by_slug_only(_newtool_index(vetoed, author=author), 4242)


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
@pytest.mark.parametrize("cross", [True, None], ids=["fork", "unknown"])
def test_a_ledger_id_on_a_fork_head_is_never_accepted(vetoed, cross):
    _held_by_slug_only(_newtool_index(vetoed, isCrossRepository=cross), 4242)


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_id_github_metadata_cannot_confirm_is_not_accepted(vetoed):
    calls = []
    idx = _newtool_index(vetoed, repos={}, calls=calls)                            # gh api repos/n/newtool fails
    _held_by_slug_only(idx, 4242)
    assert NEWTOOL_META_CALL in calls


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_id_recorded_under_a_renamed_repo_is_confirmed_through_the_redirect(vetoed):
    """The ledger records n/oldtool; GitHub renamed it n/newtool and answers the old name (redirect) with id 4242."""
    calls = []
    pr = _pr(1500, LEGACY_FILES)
    idx = _index_of(pr, vetoed, {"oid1500": _ledger(oldtool=4242)}, calls, {"n/oldtool": 4242})
    assert idx.complete and idx.hold("oldtool").repo_id == 4242
    assert idx.match("newtool", 4242).firmware == "oldtool"
    assert ("api", "repos/n/oldtool") in calls


def test_a_ledger_repo_that_is_no_plain_owner_and_name_is_never_asked_for():
    led = json.dumps({"by_id": {"oldtool": {"id": "oldtool", "repo": "n/../../user", "repo_id": 4242}}, "by_repo": {}})
    calls = []
    idx = _load(_gh([], calls=calls, ledgers={"oid1500": led}, repos={}), [_pr(1500, LEGACY_FILES)])
    assert idx.complete and idx.hold("oldtool").repo_id is None
    assert not [c for c in calls if c[:1] == ("api",) and len(c) == 2 and "/pulls/" not in c[1]]


def test_the_pr_lists_ask_for_the_author_and_whether_the_head_is_a_fork():
    fields = pending_prs.PR_LIST_FIELDS.split(",")
    assert "author" in fields and "isCrossRepository" in fields
