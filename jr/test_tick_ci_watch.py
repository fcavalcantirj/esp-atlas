"""The tick runs the CI watch (SPEC-jr-self-heal.md): before anything that may abort, never aborting,
and its nudges go to Telegram on a real run only. Uses the tick suite's fakes and its tmp checkout."""
from __future__ import annotations

from types import SimpleNamespace

import tick
from test_tick import (BOOKKEEPING, STALE, _tick_pr, checkout, gh_ok, gh_with_prs, git_ok, run,  # noqa: F401
                       wt_dir)


def test_the_tick_hands_its_preflight_to_the_watcher_and_reports_an_incident(tmp_path):
    seen = []

    def watcher(gh, slug, now, dry_run):
        seen.append((slug, dry_run))
        return {"status": "ok", "verdict": "incident", "incident": "be8b23c15820"}
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), ci_watcher=watcher)
    assert seen == [("o/r", True)] and not r.aborted
    assert r.ci_watch["incident"] == "be8b23c15820"
    assert any("CI incident be8b23c15820" in w for w in r.warnings)


def test_an_unavailable_watcher_never_aborts_the_tick(tmp_path):
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(),
               ci_watcher=lambda *a: {"status": "unavailable", "why": "required checks unreadable"})
    assert not r.aborted and any("ci_watch unavailable" in w for w in r.warnings)


def test_the_hourly_entry_point_wires_the_real_watcher(monkeypatch):
    got = {}
    monkeypatch.setattr(tick, "run_tick", lambda **kw: got.update(kw) or SimpleNamespace(aborted=None))
    tick.main(["--dry-run", "--no-telegram"])
    assert got.get("ci_watcher") is tick.default_ci_watcher


def test_the_watcher_still_runs_when_the_tick_aborts_on_a_stuck_pr(tmp_path):
    seen = []
    gh = gh_with_prs([_tick_pr(781, STALE, mergeable="CONFLICTING")],
                        files={781: BOOKKEEPING + ["data/firmware/x/firmware.md"]})
    r = run(dry_run=True, git=git_ok(tmp_path), gh=gh,
               ci_watcher=lambda *a: seen.append(a) or {"status": "ok", "verdict": "incident", "would": "record incident"})
    assert r.aborted and "needs a human" in r.aborted
    assert len(seen) == 1 and any("CI incident" in w for w in r.warnings)


NUDGING = lambda *a: {"status": "ok", "verdict": "incident", "incident": "x", "nudges": ["n1", "n2"]}  # noqa: E731


def test_a_dry_run_sends_no_nudge(tmp_path):
    sent = []
    run(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), ci_watcher=NUDGING, notifier=sent.append)
    assert sent == []


def test_a_real_tick_sends_each_nudge_to_telegram(wt_dir):
    sent = []
    r = run(git=git_ok(wt_dir), gh=gh_ok(), ci_watcher=NUDGING, notifier=sent.append)
    assert not r.aborted and "n1" in sent and "n2" in sent


def test_a_real_tick_with_telegram_off_sends_nothing(wt_dir):
    sent = []
    run(git=git_ok(wt_dir), gh=gh_ok(), ci_watcher=NUDGING, notifier=sent.append, telegram=False)
    assert sent == []
