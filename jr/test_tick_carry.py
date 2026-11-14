"""The tick carries the TTL'd decisions open tick PRs committed onto main (memory.carry_decisions): a
jr-review PR waiting for the owner, or a bookkeeping PR about to be closed as superseded, no longer holds
admit's progress. The ledgers are read at each PR's pinned head BEFORE any close; best-effort, never aborts.

Run: cd jr && python3 -m pytest test_tick_carry.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta

import memory
import pending_prs
import tick
from test_tick import JR_OWN, NOW, Proc, checkout, git_ok, gh_ok, norm, recorder, run, wt_dir  # noqa: F401
from test_tick_review_dedup import REPO, T0, _sim

LEDGER_READ = ("api", "-H", pending_prs.RAW_MEDIA)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _rej(fid, hours_ago=1, ttl_days=30):
    t = NOW - timedelta(hours=hours_ago)
    return {"id": fid, "repo": f"o/{fid}", "status": "rejected", "reason": "below_floor: 2 stars",
            "timestamp": _iso(t), "expires": _iso(t + timedelta(days=ttl_days)), "pr_ref": None}


def _ledger(*recs):
    return json.dumps({"by_id": {r["id"]: r for r in recs}, "by_repo": {r["repo"]: r["id"] for r in recs}})


def _pr(n, hours_old=0.5, files=("jr/proposed_ledger.json",), labels=(), **kw):
    return {"number": n, "createdAt": _iso(NOW - timedelta(hours=hours_old)), "headRefName": f"jr/tick-x-{n}",
            "headRefOid": f"oid{n}", "files": [{"path": f} for f in files], "changedFiles": len(files),
            "mergeable": "MERGEABLE", "labels": [{"name": x} for x in labels], "body": "", **JR_OWN, **kw}


def _gh(prs, ledgers, extra=None):
    """gh_ok plus the raw ledger read per PR (`ledgers`: {n: text or None for a failed read})."""
    script = {}
    for n, text in ledgers.items():
        script[LEDGER_READ + (f"repos/o/r/contents/jr/proposed_ledger.json?ref=oid{n}",)] = \
            (0, text) if text is not None else (1, "")
    script.update(extra or {})
    base = gh_ok(prs=json.dumps(prs))
    calls = []

    def fn(*a):
        calls.append(a)
        for prefix, (rc, out) in script.items():
            if a[:len(prefix)] == prefix:
                return Proc(returncode=rc, stdout=out)
        return base(*a)
    fn.calls = calls
    return fn


def _reads(gh):
    return [c[3] for c in gh.calls if c[:3] == LEDGER_READ]


def test_a_held_review_prs_decisions_ride_this_ticks_pr(wt_dir):
    gh = _gh([_pr(1703, labels=("jr-review",))], {1703: _ledger(_rej("a"), _rej("b"))})
    r = run(git=git_ok(wt_dir, diff="M\0jr/proposed_ledger.json\0"), gh=gh, pr_state=lambda ref: "open")
    assert not r.aborted, r.aborted
    led = memory.load(wt_dir / "jr" / "proposed_ledger.json")["by_id"]
    assert led["a"]["reason"].startswith("below_floor") and led["b"]["status"] == "rejected"
    assert r.carried == [{"pr": "#1703", "id": "a"}, {"pr": "#1703", "id": "b"}]
    assert r.publish and r.publish["published"]                       # a carry alone still ships
    body = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert "Carried 2 decision(s) from open tick PR(s) #1703" in body[body.index("--body") + 1]
    assert "carried 2" in tick.report.render_line(r)


def test_the_read_is_pinned_to_the_head_and_skips_prs_that_do_not_change_the_ledger(wt_dir):
    prs = [_pr(1, labels=("jr-review",)), _pr(2, files=("data/firmware/x/signals.json",), labels=("jr-review",))]
    gh = _gh(prs, {1: _ledger()})
    run(git=git_ok(wt_dir), gh=gh, pr_state=lambda ref: "open")
    assert _reads(gh) == ["repos/o/r/contents/jr/proposed_ledger.json?ref=oid1"]


def test_a_foreign_or_fork_tick_pr_is_never_read(wt_dir):
    foreign = {**_pr(5), "author": {"login": "someone"}}
    fork = {**_pr(6), "isCrossRepository": True}
    gh = _gh([foreign, fork], {5: _ledger(_rej("evil")), 6: _ledger(_rej("evil"))})
    r = run(git=git_ok(wt_dir), gh=gh, pr_state=lambda ref: "open")
    assert _reads(gh) == [] and r.carried == []


def test_a_superseded_prs_ledger_is_read_before_it_is_closed_and_carried(wt_dir):
    stale = _pr(7, hours_old=4)
    gh = _gh([stale], {7: _ledger(_rej("s"))},
             {("pr", "view", "7", "--json", "files"): (0, json.dumps({"files": [{"path": "jr/proposed_ledger.json"}]}))})
    r = run(git=git_ok(wt_dir, diff="M\0jr/proposed_ledger.json\0"), gh=gh, pr_state=lambda ref: "open")
    assert not r.aborted, r.aborted
    calls = list(gh.calls)
    read = next(i for i, c in enumerate(calls) if c[:3] == LEDGER_READ)
    close = next(i for i, c in enumerate(calls) if c[:2] == ("pr", "close"))
    assert read < close
    assert r.carried == [{"pr": "#7", "id": "s"}]
    assert "s" in memory.load(wt_dir / "jr" / "proposed_ledger.json")["by_id"]


def test_an_unreadable_ledger_warns_and_the_tick_goes_on(wt_dir):
    gh = _gh([_pr(1, labels=("jr-review",)), _pr(2, labels=("jr-review",))], {1: None, 2: "{not json"})
    r = run(git=git_ok(wt_dir), gh=gh, pr_state=lambda ref: "open")
    assert not r.aborted and r.carried == []
    assert any("#1" in w and "unreadable" in w for w in r.warnings)
    assert any("#2" in w and "unreadable" in w for w in r.warnings)


def test_a_dry_run_reports_the_carry_as_would_writes_only(tmp_path):
    gh = _gh([_pr(1703, labels=("jr-review",))], {1703: _ledger(_rej("a"))})
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh, pr_state=lambda ref: "open")
    assert not r.aborted and r.carried == [{"pr": "#1703", "id": "a"}]
    assert {"path": "jr/proposed_ledger.json", "field": "by_id.a", "value": "rejected"} in r.would_write
    assert all(c[:2] not in (("pr", "create"), ("pr", "close")) for c in gh.calls)


# --- end to end: the held decision is paid once and lands on main through the next AUTO tick -----

def _jr_own(sim):
    """GitHubSim's PRs carry no author; real tick PRs are the Jr bot's (pending_prs.eligible)."""
    for p in sim.prs:
        p.update(JR_OWN)


def test_a_decision_held_in_an_open_review_pr_is_never_paid_again(wt_dir, monkeypatch):
    sim = _sim(wt_dir, monkeypatch)
    r1 = sim.tick(T0)
    _jr_own(sim)
    assert r1.publish["route"] == "review"                       # held for the owner: never merges here
    held = json.loads(sim.prs[0]["ledger"])["by_id"]["tiny"]
    assert held["reason"].startswith("below_floor")
    tiny_fetches = sum(1 for c in sim.calls if c[:2] == ("api", "repos/t/tiny"))
    r2 = sim.tick(T0 + timedelta(hours=1))
    _jr_own(sim)
    assert not r2.aborted and r2.publish["route"] == "auto"
    assert {"pr": "#1481", "id": "tiny"} in r2.carried
    assert sum(1 for c in sim.calls if c[:2] == ("api", "repos/t/tiny")) == tiny_fetches   # not fetched again
    assert sim.main_rec("tiny") == held                          # verbatim, landed on main via the AUTO PR
    assert sim.prs[0]["state"] == "OPEN"                         # the owner's question still waits


def test_the_reader_itself_reads_only_the_jr_bots_own_prs():
    """Defense in depth: the caller already passes eligible PRs only; the reader re-checks."""
    gh = _gh([], {1: _ledger(_rej("ok")), 5: _ledger(_rej("evil")), 6: _ledger(_rej("evil"))})
    prs = [_pr(1), {**_pr(5), "author": {"login": "someone"}}, {**_pr(6), "isCrossRepository": True}]
    sources, warnings = tick._open_pr_ledgers(gh, "o/r", prs)
    assert [ref for ref, _ in sources] == ["#1"] and warnings == []
    assert _reads(gh) == ["repos/o/r/contents/jr/proposed_ledger.json?ref=oid1"]
