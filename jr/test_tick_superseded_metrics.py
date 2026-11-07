"""Retiring Jr's in-catalog popularity writer (jr/tick.py, jr/superseded_metrics.py).

GitHub star/fork counts are published by the separate runtime JSON publisher
(jr/runtime_popularity.py), so the hourly tick no longer runs jr/stage_popularity_refresh. A tick
PR left behind that ONLY refreshed popularity in existing catalogued firmware.md records is
superseded metrics: when stale or conflicting, the preflight closes it (no rejection is recorded:
those ids are already merged) instead of aborting every later tick. Anything else stays stuck.
All on the recorders of jr/test_tick.py: fake git, fake gh, no network.

Run: cd jr && python3 -m pytest test_tick_superseded_metrics.py -v
"""
from __future__ import annotations

import base64
import json

import memory
import stage_popularity_refresh
import superseded_metrics
import tick
from test_tick import (FRESH, NOW, STALE, Proc, _closes, _fake_stage_modules, _tick_pr, checkout,  # noqa: F401
                       gh_with_prs, git_ok, norm, run, wt_dir)
from test_tick_review import _review_pr

RECORD = """---
id: {fid}
type: firmware
name: Tool
url: https://github.com/o/{fid}
category: multi
popularity:
  stars: 42
  forks: 0
  as_of: '2026-09-20'
socs:
- esp32
sources:
- field: '*'
  url: https://github.com/o/{fid}
  verified: '2026-09-20'
- field: popularity
  url: https://github.com/o/{fid}
  verified: '2026-09-20'
summary: A tool.
---

Tool firmware.
"""


def refreshed(old: str, fid: str) -> str:
    """The legacy stage's edit (PR 1530's shape): counts + GitHub identity + popularity.* sources."""
    new = old.replace("  stars: 42\n  forks: 0\n  as_of: '2026-09-20'\n",
                      "  stars: 43\n  forks: 0\n  as_of: '2026-11-07'\n  github_repo_id: 645739110\n"
                      "  github_as_of: '2026-11-07T16:00:55Z'\n")
    new = new.replace("- field: popularity\n  url: https://github.com/o/{0}\n  verified: '2026-09-20'\n".format(fid),
                      "- field: popularity\n  url: https://github.com/o/{0}\n  verified: '2026-11-07'\n".format(fid))
    return new.replace("summary: A tool.\n", "".join(
        f"- field: popularity.{k}\n  url: https://github.com/o/{fid}\n  verified: '2026-11-07'\n"
        for k in ("forks", "github_as_of", "github_repo_id", "stars")) + "summary: A tool.\n")


def fw(fid: str) -> str:
    return f"data/firmware/{fid}/firmware.md"


def gh_metrics(prs, files, statuses=None, base=None, head=None, compare_rc=0, refs_rc=0):
    """gh_with_prs plus the read-only diff reads: `pr view N --json baseRefName,headRefOid`, the
    compare API (merge base + per-file status) and the contents API at both commits."""
    inner = gh_with_prs(prs, files=files)
    statuses, base, head = statuses or {}, base or {}, head or {}

    def fn(*args):
        if args[:2] == ("pr", "view") and args[3:] == ("--json", "baseRefName,headRefOid"):
            inner.calls.append(args)
            n = int(args[2])
            return Proc(returncode=refs_rc, stdout=json.dumps({"baseRefName": "main", "headRefOid": f"head{n}"}))
        if args[:1] == ("api",) and "/compare/main...head" in args[1]:
            inner.calls.append(args)
            n = int(args[1].rsplit("head", 1)[1])
            listed = [{"filename": p, "status": statuses.get(p, "modified")} for p in files.get(n, [])]
            return Proc(returncode=compare_rc, stdout=json.dumps({"merge_base": f"base{n}", "files": listed}))
        if args[:1] == ("api",) and "/contents/" in args[1]:
            inner.calls.append(args)
            path, ref = args[1].split("/contents/", 1)[1].split("?ref=")
            text = (base if ref.startswith("base") else head).get(path)
            if text is None:
                return Proc(returncode=1, stdout="", stderr="HTTP 404")
            return Proc(stdout=base64.b64encode(text.encode()).decode() + "\n")
        return inner(*args)
    fn.calls = inner.calls
    return fn


IDS = ["clawdmeter", "rogueduck"]
OLD = {fw(f): RECORD.format(fid=f) for f in IDS}
NEW = {fw(f): refreshed(RECORD.format(fid=f), f) for f in IDS}
METRICS_PR = [fw(f) for f in IDS] + ["jr/proposed_ledger.json"]


# --- (1) the hourly path no longer writes popularity into the catalog --------------------------

def test_hourly_stages_no_longer_run_the_in_catalog_popularity_writer(monkeypatch):
    calls = []
    _fake_stage_modules(monkeypatch, calls)
    for split in ({"backfill": 4, "firmware": 2}, {"backfill": 0, "firmware": 0}, {"backfill": 0, "firmware": 3}):
        for fn in tick.hourly_stages(split):
            fn(None)
    assert ("popularity_refresh",) not in calls and calls


def test_the_legacy_module_and_the_runtime_publisher_stay_importable_and_untouched():
    import runtime_popularity
    assert callable(stage_popularity_refresh.run)            # kept: runtime_popularity reuses it
    assert runtime_popularity.legacy is stage_popularity_refresh
    assert runtime_popularity.BRANCH == "runtime-popularity" and runtime_popularity.FILENAME == "popularity.json"


# --- (2) the popularity-only predicate ---------------------------------------------------------

def test_a_legacy_refresh_is_popularity_only():
    assert superseded_metrics.popularity_only(OLD[fw("clawdmeter")], NEW[fw("clawdmeter")])


def test_a_non_popularity_field_change_is_not_popularity_only():
    old = OLD[fw("clawdmeter")]
    assert not superseded_metrics.popularity_only(old, NEW[fw("clawdmeter")].replace("category: multi", "category: tool"))
    assert not superseded_metrics.popularity_only(old, NEW[fw("clawdmeter")].replace("summary: A tool.", "summary: Other."))


def test_a_body_or_non_popularity_source_change_is_not_popularity_only():
    old, new = OLD[fw("clawdmeter")], NEW[fw("clawdmeter")]
    assert not superseded_metrics.popularity_only(old, new.replace("Tool firmware.", "Tool firmware!"))
    assert not superseded_metrics.popularity_only(old, new.replace("- field: '*'\n  url: https://github.com/o/clawdmeter\n  verified: '2026-09-20'",
                                                                   "- field: '*'\n  url: https://github.com/o/clawdmeter\n  verified: '2026-11-07'"))
    assert not superseded_metrics.popularity_only(old, new.replace("- field: popularity.stars", "- field: socs"))


def test_an_unreadable_record_is_not_popularity_only():
    assert not superseded_metrics.popularity_only(None, NEW[fw("clawdmeter")])
    assert not superseded_metrics.popularity_only(OLD[fw("clawdmeter")], "no frontmatter")
    assert not superseded_metrics.popularity_only(OLD[fw("clawdmeter")], NEW[fw("clawdmeter")].replace("sources:", "sources: oops\nx:"))


# --- (2) triage: stale/conflicting metrics-only PRs are closed, everything else stays stuck --------

def test_a_stale_metrics_only_tick_pr_is_closed_and_the_tick_proceeds(wt_dir):
    gh = gh_metrics([_tick_pr(1530, STALE, mergeable="CONFLICTING")], {1530: METRICS_PR}, base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted
    (close,) = _closes(gh)
    assert close[2] == "1530" and "--delete-branch" in close
    comment = close[close.index("--comment") + 1]
    assert "runtime" in comment.lower() and "popularity" in comment.lower() and "no rejection" in comment.lower()
    assert any("#1530" in w and "metrics" in w for w in r.warnings)


def test_a_stale_mergeable_metrics_only_pr_is_closed_too(wt_dir):
    gh = gh_metrics([_tick_pr(1531, STALE)], {1531: METRICS_PR}, base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and [c[2] for c in _closes(gh)] == ["1531"]


def test_the_diff_is_read_against_the_merge_base_with_read_only_calls(wt_dir):
    gh = gh_metrics([_tick_pr(1530, STALE)], {1530: METRICS_PR}, base=OLD, head=NEW)
    run(git=git_ok(wt_dir), gh=gh)
    reads = [c for c in gh.calls if c[:1] == ("api",) and "/contents/" in c[1]]
    assert sorted(c[1] for c in reads) == sorted(f"repos/o/r/contents/{p}?ref={ref}"
                                                 for p in OLD for ref in ("base1530", "head1530"))
    assert any(c[:2] == ("api", "repos/o/r/compare/main...head1530") for c in gh.calls)


def test_dry_run_only_reports_the_metrics_pr_it_would_close(tmp_path):
    gh = gh_metrics([_tick_pr(1530, STALE)], {1530: METRICS_PR}, base=OLD, head=NEW)
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh)
    assert not r.aborted and _closes(gh) == []
    assert any("would close" in w and "#1530" in w and "metrics" in w for w in r.warnings)


def test_a_pr_adding_a_new_firmware_is_never_auto_closed(wt_dir):
    files = METRICS_PR + [fw("brand-new")]
    head = {**NEW, fw("brand-new"): RECORD.format(fid="brand-new")}
    gh = gh_metrics([_tick_pr(1532, STALE, mergeable="CONFLICTING")], {1532: files},
                    statuses={fw("brand-new"): "added"}, base=OLD, head=head)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert _closes(gh) == [] and "#1532" in r.aborted and "needs a human" in r.aborted


def test_a_metrics_pr_that_also_changes_a_non_popularity_field_stays_stuck(wt_dir):
    head = {**NEW, fw("rogueduck"): NEW[fw("rogueduck")].replace("category: multi", "category: tool")}
    gh = gh_metrics([_tick_pr(1533, STALE)], {1533: METRICS_PR}, base=OLD, head=head)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert _closes(gh) == [] and "#1533" in r.aborted and "needs a human" in r.aborted


def test_a_metrics_pr_with_a_recipe_stays_stuck_without_reading_any_diff(wt_dir):
    gh = gh_metrics([_tick_pr(1534, STALE)], {1534: METRICS_PR + ["data/recipes/b__clawdmeter/recipe.md"]},
                    base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert _closes(gh) == [] and "needs a human" in r.aborted
    assert not any(c[:1] == ("api",) and ("/compare/" in c[1] or "/contents/" in c[1]) for c in gh.calls)


def test_an_unreadable_diff_keeps_the_pr_stuck(wt_dir):
    for kw in ({"refs_rc": 1}, {"compare_rc": 1}, {"base": {}, "head": NEW}, {"base": OLD, "head": {}}):
        kw = {"base": OLD, "head": NEW, **kw}
        gh = gh_metrics([_tick_pr(1535, STALE)], {1535: METRICS_PR}, **kw)
        r = run(git=git_ok(wt_dir), gh=gh)
        assert _closes(gh) == [] and "needs a human" in r.aborted, kw


def test_a_compare_listing_other_files_than_the_pr_keeps_it_stuck(wt_dir):
    gh = gh_metrics([_tick_pr(1536, STALE)], {1536: METRICS_PR}, base=OLD, head=NEW)

    def fn(*args):
        if args[:1] == ("api",) and "/compare/" in args[1]:
            gh.calls.append(args)
            return Proc(stdout=json.dumps({"merge_base": "base1536",
                                           "files": [{"filename": fw("clawdmeter"), "status": "modified"}]}))
        return gh(*args)
    fn.calls = gh.calls
    r = run(git=git_ok(wt_dir), gh=fn)
    assert _closes(gh) == [] and "needs a human" in r.aborted


def test_a_young_mergeable_metrics_pr_is_left_alone_and_its_diff_never_read(wt_dir):
    gh = gh_metrics([_tick_pr(1537, FRESH)], {1537: METRICS_PR}, base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and _closes(gh) == []
    assert not any(c[:1] == ("api",) and "/compare/" in c[1] for c in gh.calls)


# --- (3) closing records no rejection ----------------------------------------------------------

def test_closing_a_metrics_pr_leaves_the_ledger_unchanged(wt_dir):
    led = {"by_id": {f: {"id": f, "repo": f"o/{f}", "status": "merged", "reason": None, "pr_ref": "#100",
                         "timestamp": "2026-10-01T00:00:00+00:00", "expires": None} for f in IDS},
           "by_repo": {f"o/{f}": f for f in IDS}}
    (wt_dir / "jr" / "proposed_ledger.json").write_text(json.dumps(led, indent=2) + "\n")
    for f in IDS:                                    # the worktree's catalog: these ids are catalogued
        (wt_dir / fw(f)).parent.mkdir(parents=True)
        (wt_dir / fw(f)).write_text(OLD[fw(f)])
    gh = gh_metrics([_tick_pr(1530, STALE, mergeable="CONFLICTING")], {1530: METRICS_PR}, base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh, pr_state=lambda ref: "closed")   # the PR now reads closed
    assert not r.aborted and [c[2] for c in _closes(gh)] == ["1530"]
    assert memory.load(wt_dir / "jr" / "proposed_ledger.json")["by_id"] == led["by_id"]
    assert r.memory.get("rejected") == 0 and r.publish is None


# --- (4) a jr-review PR stays skipped ----------------------------------------------------------

def test_a_jr_review_metrics_pr_is_skipped_never_closed_and_never_diffed(wt_dir):
    gh = gh_metrics([_review_pr(1538, 30, mergeable="CONFLICTING")], {1538: METRICS_PR}, base=OLD, head=NEW)
    r = run(git=git_ok(wt_dir), gh=gh)
    assert not r.aborted and _closes(gh) == []
    assert not any(c[:1] == ("api",) and "/compare/" in c[1] for c in gh.calls)
