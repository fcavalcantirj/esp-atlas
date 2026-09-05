"""Tests for jr/report.py — the one-line Telegram report and the deterministic PR body."""
from __future__ import annotations

from datetime import datetime, timezone

import report

NOW = datetime(2026, 9, 5, 4, 7, tzinfo=timezone.utc)


def _r(**kw):
    return report.TickReport(when=NOW, **kw)


def test_line_for_a_quiet_tick_says_nothing_to_do_and_carries_every_field():
    line = report.render_line(_r(boards_pct=42.5, overall_pct=68.2,
                                 allocation="boards 42.5% -> A0/B0 (phase 2: no content stages)",
                                 memory={"expired": 1, "merged": 2, "rejected": 0, "removed": 0},
                                 budget="gh calls 4/150 · 3.2s/360s"))
    assert line == ("🤖 jr-tick 2026-09-05 04:07 UTC: boards 42.5% (overall 68.2%) · "
                    "boards 42.5% -> A0/B0 (phase 2: no content stages) · admitted 0 · rejects none · "
                    "memory expired 1 / merged 2 / rejected 0 / removed 0 · nothing to do · gh calls 4/150 · 3.2s/360s")


def test_line_for_a_dry_run_marks_it_and_shows_warnings():
    line = report.render_line(_r(dry_run=True, boards_pct=42.5, overall_pct=68.2, allocation="a",
                                 warnings=["branch protection: main is not protected"], budget="b"))
    assert line.startswith("🤖 jr-tick (dry-run) 2026-09-05 04:07 UTC:")
    assert "⚠ branch protection: main is not protected" in line
    assert "nothing to do" in line


def test_line_for_an_aborted_tick_is_short_and_says_why():
    line = report.render_line(_r(aborted="GitHub rate limit low: 12 < 500", budget="gh calls 1/150 · 0.4s/360s"))
    assert line == "🛑 jr-tick 2026-09-05 04:07 UTC: aborted — GitHub rate limit low: 12 < 500 · gh calls 1/150 · 0.4s/360s"


def test_line_for_a_published_tick_links_the_pr_and_the_merge_mode():
    r = _r(boards_pct=50.0, overall_pct=70.0, allocation="a", admitted=2, rejects={"below_floor": 3, "fork": 1},
           stages=[{"name": "discover", "paths": ["data/firmware/x"], "summary": "s", "needs_human": False}],
           guard={"ok": True, "output": ""}, revalidate={"ok": True, "status": 200},
           publish={"published": True, "pr_url": "https://github.com/o/r/pull/1", "auto_merge": True, "reason": ""},
           budget="b")
    line = report.render_line(r)
    assert "admitted 2 · rejects below_floor 3, fork 1" in line
    assert "guard green · revalidate ok · PR https://github.com/o/r/pull/1 · auto-merge" in line
    r.publish["auto_merge"] = False; r.publish["reason"] = "needs_human: auto-merge withheld"
    assert "PR https://github.com/o/r/pull/1 · needs_human: auto-merge withheld" in report.render_line(r)


def test_pr_body_lists_stages_paths_memory_and_the_standing_rule():
    r = _r(base_sha="6190d21", boards_pct=42.5, overall_pct=68.2, allocation="alloc",
           stages=[{"name": "discover", "paths": ["data/firmware/x", "data/recipes/b__x"], "summary": "1 admitted", "needs_human": True}],
           rejects={"fork_of_catalogued": 2}, memory={"expired": 0, "merged": 1, "rejected": 0, "removed": 0},
           guard={"ok": True, "output": ""}, budget="gh calls 9/150 · 40.0s/360s")
    body = report.render_pr_body(r)
    assert body.startswith("EspAtlas Jr tick — 2026-09-05 04:07 UTC")
    assert "Base: `6190d21` · boards 42.5% · overall 68.2%" in body
    assert "- **discover** — 1 admitted ⚠️ needs a human" in body
    assert "  - `data/firmware/x`" in body and "  - `data/recipes/b__x`" in body
    assert "- fork_of_catalogued: 2" in body
    assert "Memory: expired 0, merged 1, rejected 0, removed 0 (ledger committed with this PR)." in body
    assert "Guard: green" in body
    assert "no record is deleted by a tick until the G2 guard is in CI" in body


def test_paths_are_deduplicated_across_stages_and_needs_human_aggregates():
    r = _r(stages=[{"name": "a", "paths": ["p1", "p2"], "needs_human": False},
                   {"name": "b", "paths": ["p2", "p3"], "needs_human": True}])
    assert r.paths == ["p1", "p2", "p3"] and r.needs_human
