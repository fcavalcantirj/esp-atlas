"""Tests for the tick's side of risk-based review routing (SPEC-jr-review-routing.md).

An open tick PR labelled `jr-review` is waiting for the owner ON PURPOSE: the preflight must never
read it as stuck (no TickAbort, whatever its age) and never close it as superseded. Too many of
them open caps the review-producing stages. All on the recorders of jr/test_tick.py: fake git,
fake gh, no network.

Run: cd jr && python3 -m pytest test_tick_review.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta

import review_routing
import tick
from test_tick import (BOOKKEEPING, NOW, STALE, Proc, _closes, _fake_stage_modules, _stage, _tick_pr, checkout,  # noqa: F401
                       gh_with_prs, git_ok, recorder, run, wt_dir)


def _iso(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _review_pr(number, hours, mergeable="MERGEABLE"):
    return {**_tick_pr(number, _iso(hours), mergeable), "labels": [{"name": "jr-review"}]}


def _git_diff(wt_dir, *pairs):
    """git_ok with a scripted staged diff."""
    base = git_ok(wt_dir)
    z = "".join(f"{st}\0{path}\0" for st, path in pairs)

    def fn(*args):
        norm = args[2:] if args[:1] == ("-C",) else args
        if norm == ("diff", "--cached", "--name-status", "--no-renames", "-z"):
            base.calls.append(args)
            return Proc(stdout=z)
        return base(*args)
    fn.calls = base.calls
    return fn


# --- triage: a jr-review PR is never stuck, never closed -------------------------------------------

def test_a_jr_review_pr_aged_30h_does_not_abort_the_tick_and_is_not_closed(wt_dir):
    gh = gh_with_prs([_review_pr(901, 30)], files={901: ["data/firmware/x/firmware.md"]})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and _closes(gh) == []
    assert [(p["number"], p["age_hours"]) for p in r.review_prs] == [(901, 30.0)]


def test_a_conflicting_bookkeeping_only_jr_review_pr_is_never_closed_as_superseded(wt_dir):
    gh = gh_with_prs([_review_pr(902, 30, mergeable="CONFLICTING")], files={902: BOOKKEEPING})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and _closes(gh) == []
    assert not any("superseded" in w for w in r.warnings)


def test_an_unlabelled_4h_data_pr_still_aborts_the_tick(wt_dir):
    pr = {**_tick_pr(903, STALE), "labels": [{"name": "veto"}]}
    gh = gh_with_prs([pr, _review_pr(904, 30)], files={903: ["data/firmware/x/firmware.md"], 904: ["data/recipes/b__x/recipe.md"]})
    r = run(git=git_ok(wt_dir), gh=gh)
    assert r.aborted.startswith("a Jr tick PR has been open > 3 h: #903") and "needs a human" in r.aborted
    assert _closes(gh) == []


def test_the_pr_list_query_asks_for_labels():
    gh = recorder({("pr", "list"): (0, "[]")})
    tick._list_open_prs(gh)
    (call,) = gh.calls
    assert "labels" in call[call.index("--json") + 1].split(",")
    # gh's default is 30, newest first; jr-review PRs are the oldest open ones and must stay visible
    assert int(call[call.index("--limit") + 1]) >= 500


# --- the cap ---------------------------------------------------------------------------------------

def test_at_the_cap_the_tick_skips_review_producing_stages_and_reports_it(wt_dir, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    prs = [_review_pr(910 + i, 5 + i) for i in range(review_routing.MAX_OPEN_REVIEW_PRS)]
    r = run(git=git_ok(wt_dir), gh=gh_with_prs(prs), stages=None)
    assert not r.aborted and calls == [("popularity_refresh",)]
    assert any("jr-review cap reached (10/10 open)" in w and "skipped 4 review-producing stage(s)" in w for w in r.warnings)
    assert r.review_capped


def test_below_the_cap_the_stages_run(wt_dir, monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    prs = [_review_pr(920 + i, 5) for i in range(review_routing.MAX_OPEN_REVIEW_PRS - 1)]
    r = run(git=git_ok(wt_dir), gh=gh_with_prs(prs), stages=None)
    assert not r.aborted and len(calls) == 5 and not r.review_capped


def test_the_cap_keeps_a_stage_that_declares_it_never_produces_review(wt_dir):
    ran = []

    def safe(ctx):
        ran.append("safe")
        return tick.StageResult("safe")
    safe.produces_review = False
    risky = _stage(["data/firmware/x"])
    prs = [_review_pr(930 + i, 5) for i in range(3)]
    r = run(git=git_ok(wt_dir), gh=gh_with_prs(prs), stages=[safe, risky], review_cap=3)
    assert ran == ["safe"] and [s["name"] for s in r.stages] == ["safe"]
    assert any("skipped 1 review-producing stage(s)" in w for w in r.warnings)


def test_the_cap_counts_jr_review_prs_on_any_branch(wt_dir):
    demand = {"number": 940, "createdAt": _iso(2), "headRefName": "jr/demand-20260905-0930", "labels": [{"name": "jr-review"}]}
    gh = gh_with_prs([demand, _review_pr(941, 2)])
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_stage(["data/firmware/x"])], review_cap=2)
    assert r.review_capped and r.stages == []


# --- publish through the tick: a new firmware PR goes to review -------------------------------------

def test_a_new_firmware_tick_pr_is_labelled_jr_review_withheld_and_notified(wt_dir):
    sent = []
    gh = gh_with_prs([])
    r = run(git=git_ok(wt_dir), gh=gh, stages=[_stage(["data/firmware/x"])], notifier=lambda t: sent.append(t))
    assert not r.aborted and r.publish["published"] and not r.publish["auto_merge"]
    assert r.publish["route"] == "review" and r.publish["labelled"]
    assert ("pr", "edit", "https://github.com/o/r/pull/1", "--add-label", "jr-review") in gh.calls
    assert all(c[:2] != ("pr", "merge") for c in gh.calls)
    assert len(sent) == 1 and "jr-review" in sent[0]


def test_a_bookkeeping_only_tick_pr_stays_auto(wt_dir):
    gh = gh_with_prs([])
    r = run(git=_git_diff(wt_dir, ("M", "docs/telemetry/data-trend.jsonl")), gh=gh,
            stages=[_stage(["docs/telemetry/data-trend.jsonl"])])
    assert r.publish["route"] == "auto" and r.publish["auto_merge"]
    assert all(c[:2] != ("pr", "edit") for c in gh.calls)


def test_the_tick_hands_its_stage_review_items_to_the_classifier(wt_dir):
    review = [{"id": "zap", "repo": "z/zap", "kind": "release_bin", "url": "u", "why": "w"}]

    def stage(ctx):
        return tick.StageResult("admit_topics", paths=["docs/telemetry/data-trend.jsonl"], review=review)
    r = run(git=_git_diff(wt_dir, ("M", "docs/telemetry/data-trend.jsonl")), gh=gh_with_prs([]), stages=[stage])
    assert r.publish["route"] == "review" and any("z/zap" in x for x in r.publish["review_reasons"])


# --- the report lists the open jr-review PRs and their age ------------------------------------------

def test_the_report_line_lists_open_jr_review_prs_with_their_age(wt_dir, capsys):
    gh = gh_with_prs([_review_pr(950, 30), _review_pr(951, 4.5, mergeable="CONFLICTING")])
    r = run(git=git_ok(wt_dir), gh=gh)
    line = capsys.readouterr().out.strip()
    assert line == tick.report.render_line(r)
    assert "jr-review open 2: #950 30h, #951 4h (conflicting)" in line


def test_a_jr_review_pr_with_an_unreadable_age_is_still_listed_and_never_stuck(wt_dir):
    pr = {**_review_pr(960, 0), "createdAt": "garbage"}
    r = run(git=git_ok(wt_dir), gh=gh_with_prs([pr]))
    assert not r.aborted and r.review_prs[0]["number"] == 960 and r.review_prs[0]["age_hours"] is None
    assert "#960 ?h" in tick.report.render_line(r)


def test_dry_run_reports_the_open_review_prs_and_the_cap(tmp_path):
    prs = [_review_pr(970, 30)]
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_with_prs(prs), stages=[_stage(["data/firmware/x"])], review_cap=1)
    assert not r.aborted and r.review_capped and r.stages == []
    assert json.loads(json.dumps(r.review_prs))[0]["number"] == 970
