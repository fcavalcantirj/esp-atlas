"""An incomplete pending-PR inventory degrades the tick instead of aborting it (2026-11-18).

Four hourly ticks aborted on one firmware's identity gap in one open PR (#1839, `wled`), and with them
every lane that never reads firmware identity: board backfill, reconciliation, telemetry. Now an
incomplete inventory skips exactly what could act on an unverified hold — every stage not declared
`firmware_free`, and the two steps that copy content out of open PRs' committed ledgers (hydration and
the decision carry, the path a substituted ledger pair would ride) — and the rest of the tick runs and
publishes. GitHub unreadable stays a full abort. The degraded reason goes to the abort watcher, so the
same gap two ticks running is a heal incident (SPEC-jr-self-heal.md §1c). Fake git/gh (test_tick).
"""
from __future__ import annotations

import json

import pytest

import tick
from test_tick import git_ok, gh_ok, run, wt_dir  # noqa: F401 — wt_dir is a fixture

ONE_PR = json.dumps([{"number": 5, "createdAt": "2026-09-05T03:00:00Z", "headRefName": "feat/x", "files": [],
                      "changedFiles": 0, "author": {"login": "someone"}, "isCrossRepository": False}])


def _stage(name, calls, free=False):
    def s(ctx):
        calls.append(name)
        return tick.StageResult(name=name)
    if free:
        s.firmware_free = True
    return s


@pytest.fixture
def cut_list(monkeypatch):
    """The open-PR list returns as many PRs as its limit: a Jr PR may be unseen, the inventory is incomplete."""
    monkeypatch.setattr(tick, "OPEN_PR_LIMIT", 1)


def test_an_incomplete_inventory_runs_only_the_firmware_free_stages(wt_dir, cut_list):
    calls = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=ONE_PR), pr_state=lambda ref: "open",
            stages=[_stage("backfill", calls, free=True), _stage("admit", calls), _stage("boardmap", calls)])
    assert not r.aborted, r.aborted
    assert r.degraded.startswith("pending-PR inventory incomplete") and "limit of 1" in r.degraded
    assert calls == ["backfill"]
    assert any(w.startswith("degraded:") for w in r.warnings)


def test_a_degraded_tick_copies_nothing_out_of_open_prs(wt_dir, cut_list, monkeypatch):
    seen = []
    monkeypatch.setattr(tick, "hydrate_open_pr_ledger", lambda *a, **k: seen.append("hydrate") or [])
    monkeypatch.setattr(tick.memory, "carry_decisions", lambda *a, **k: seen.append("carry") or [])
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=ONE_PR), pr_state=lambda ref: "open", stages=[])
    assert r.degraded and seen == []


def test_a_complete_inventory_runs_every_stage_and_is_not_degraded(wt_dir):
    calls = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(), pr_state=lambda ref: "open",
            stages=[_stage("backfill", calls, free=True), _stage("admit", calls)])
    assert not r.aborted and not r.degraded and calls == ["backfill", "admit"]


def test_the_degraded_reason_reaches_the_abort_watcher_and_the_report_line(wt_dir, cut_list):
    got = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(prs=ONE_PR), pr_state=lambda ref: "open", stages=[],
            abort_watcher=lambda reason, now, dry: got.append(reason) or {"status": "ok", "incidents": [], "resolved": [], "nudges": []})
    assert got == [r.degraded] and got[0].startswith("pending-PR inventory incomplete")
    assert "degraded — pending-PR inventory incomplete" in tick.report.render_line(r)


def test_a_degraded_tick_tells_the_owner(wt_dir, cut_list):
    sent = []
    run(git=git_ok(wt_dir), gh=gh_ok(prs=ONE_PR), pr_state=lambda ref: "open", stages=[], notifier=sent.append)
    assert any("degraded" in s for s in sent)


def test_only_the_backfill_stage_is_firmware_free_in_the_hourly_list():
    flags = [getattr(s, "firmware_free", False) for s in tick.hourly_stages({"backfill": 2, "firmware": 3})]
    assert flags == [True, False, False, False]          # backfill · admit · boardmap · admit_topics
