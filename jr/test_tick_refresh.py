"""The tick runs the review-PR refresh (jr/review_refresh.py, SPEC-jr-review-routing.md §8) after its own
publish: only on its own CONFLICTING jr-review PRs, at most REFRESH_MAX a tick, never aborting the tick."""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import tick
from test_tick import JR_OWN, NOW, git_ok, gh_ok, run, wt_dir  # noqa: F401


def _pr(n, mergeable="CONFLICTING", labels=("jr-review",)):
    return {"number": n, "createdAt": (NOW - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "headRefName": f"jr/tick-x-{n}", "headRefOid": f"oid{n}", "mergeable": mergeable,
            "labels": [{"name": x} for x in labels], "files": [], "changedFiles": 0, **JR_OWN}


def _refresher(calls, result=None, boom=False):
    def fn(pr, *, git, gh, now, dry_run):
        calls.append((pr["number"], dry_run))
        if boom:
            raise RuntimeError("git exploded")
        return result or {"pr": pr["number"], "status": "refreshed", "why": "1 bookkeeping conflict(s)", "head": "abc"}
    return fn


def test_only_conflicting_jr_review_prs_are_refreshed_and_at_most_the_cap(wt_dir):
    prs = [_pr(1), _pr(2, mergeable="MERGEABLE"), _pr(3, labels=()), *[_pr(n) for n in range(4, 4 + tick.REFRESH_MAX + 2)]]
    calls = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=json.dumps(prs)), refresher=_refresher(calls), pr_state=lambda ref: "open")
    assert not r.aborted, r.aborted
    assert [n for n, _ in calls] == [1, 4, 5][:tick.REFRESH_MAX]
    assert [x["pr"] for x in r.refreshed] == [n for n, _ in calls]
    assert "refreshed #1" in tick.report.render_line(r)


def test_a_dry_run_only_asks_what_it_would_refresh(tmp_path):
    calls = []
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(prs=json.dumps([_pr(1)])), refresher=_refresher(calls),
            pr_state=lambda ref: "open")
    assert calls == [(1, True)]


def test_a_failing_refresh_warns_and_never_aborts_the_tick(wt_dir):
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=json.dumps([_pr(1)])), refresher=_refresher([], boom=True),
            pr_state=lambda ref: "open")
    assert not r.aborted and any("refresh #1 failed" in w for w in r.warnings)


def test_the_hourly_entry_point_wires_the_real_refresher(monkeypatch):
    got = {}
    monkeypatch.setattr(tick, "run_tick", lambda **kw: got.update(kw) or SimpleNamespace(aborted=None))
    tick.main(["--dry-run", "--no-telegram"])
    assert got.get("refresher") is tick.review_refresh.refresh
