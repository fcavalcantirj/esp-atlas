"""Tests for jr/report.py — the one-line Telegram report and the deterministic PR body."""
from __future__ import annotations

from datetime import datetime, timezone

import report

NOW = datetime(2026, 9, 5, 4, 7, tzinfo=timezone.utc)


def _r(**kw):
    return report.TickReport(when=NOW, **kw)


def test_line_for_a_quiet_tick_says_nothing_to_do_and_carries_every_field():
    line = report.render_line(_r(boards_pct=42.5, overall_pct=68.2,
                                 allocation="boards 42.5% -> A0/B0 (no content stages registered)",
                                 memory={"expired": 1, "merged": 2, "rejected": 0, "removed": 0},
                                 budget="gh calls 4/150 · 3.2s/360s"))
    assert line == ("🤖 jr-tick 2026-09-05 04:07 UTC: boards 42.5% (overall 68.2%) · "
                    "boards 42.5% -> A0/B0 (no content stages registered) · admitted 0 · rejects none · "
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
    assert "admitted 2 · rejects below_floor 3, fork 1" in line and " · discover: s" in line
    assert "guard green · revalidate ok · PR https://github.com/o/r/pull/1 · auto-merge" in line
    r.publish["auto_merge"] = False; r.publish["reason"] = "needs_human: auto-merge withheld"
    assert "PR https://github.com/o/r/pull/1 · needs_human: auto-merge withheld" in report.render_line(r)


def test_pr_body_reads_as_a_verdict_with_gate_checklists_counts_and_a_folded_stage_log():
    """PR #149 was 10.7 KB of 'x: skip y' — a human could not validate it by reading. The body
    now says what is proposed and which gates it passed, counts the skips, and folds the log."""
    fw = {"kind": "firmware", "id": "taskhub-for-sticks3", "name": "AI TaskHub", "url": "https://github.com/s/Taskhub-for-StickS3",
          "stars": 27, "forks": 3, "fork": False, "archived": False, "license": "MIT", "board": "m5stick-s3", "chip": "esp32-s3",
          "recipe": "m5stick-s3__taskhub-for-sticks3", "evidence": "named in the repository name/description", "needs_human": False, "submission": None}
    rec = {"kind": "recipes", "firmware": "draftling", "written": ["m5stack-papers3__draftling", "freenove-fnk0104a__draftling"], "existing": 1,
           "socs_added": [], "signals": 9, "unresolved": 1, "kinds": {"asset": 9}, "notes": ["latest release v1.0.2 has no binaries; read v1.0.1 instead"]}
    r = _r(base_sha="6190d21", boards_pct=42.5, overall_pct=68.2, allocation="boards 42.5% -> A2/B4 (hourly)",
           stages=[{"name": "admit", "paths": ["data/firmware/taskhub-for-sticks3/firmware.md"], "summary": "skipped 313 launcher entries: repo_unresolved 179", "needs_human": False, "items": [fw]},
                   {"name": "boardmap", "paths": ["data/recipes/m5stack-papers3__draftling"], "summary": "draftling: +2 recipe(s)", "needs_human": True, "items": [rec]}],
           rejects={"repo_unresolved": 179, "below_floor": 81}, memory={"expired": 0, "merged": 1, "rejected": 0, "removed": 0},
           guard={"ok": True, "output": ""}, budget="gh calls 146/150 · 190.0s/360s")
    body = report.render_pr_body(r)
    assert body.startswith("EspAtlas Jr tick — 2026-09-05 04:07 UTC")
    assert "Base `6190d21` · boards 42.5% · overall 68.2% · boards 42.5% -> A2/B4 (hourly)" in body
    # the firmware checklist
    assert "- **AI TaskHub** (`taskhub-for-sticks3`) — https://github.com/s/Taskhub-for-StickS3" in body
    assert "✅ public GitHub repository, not a fork, not archived · 27 ★ / 3 forks (floor: 25 stars or 25 forks) · license MIT" in body
    assert "✅ not already catalogued (repository, name tokens, repository id)" in body
    assert "✅ board `m5stick-s3` (esp32-s3): named in the repository name/description → recipe `m5stick-s3__taskhub-for-sticks3`, status unverified" in body
    # the recipes checklist
    assert "- **draftling** — +2 recipe(s), 1 existing kept" in body
    assert "  - ✅ `m5stack-papers3__draftling` — board named in the repo's own build files, cited; status unverified" in body
    assert "  - evidence: 9 signal(s) — asset 9; 1 token(s) name no catalogued board" in body
    assert "  - note: latest release v1.0.2 has no binaries; read v1.0.1 instead" in body
    # skips are counts, never a list
    assert "### Skipped this tick" in body and "- repo_unresolved: 179" in body and "- below_floor: 81" in body
    assert "x: skip" not in body
    # one summary line + the standing rule + the folded log
    assert "1 record(s) · 3 recipe(s) · guard green · memory expired 0 / merged 1 / rejected 0 / removed 0 · gh calls 146/150 · 190.0s/360s" in body
    assert "**Merge = accept. Close = veto**" in body
    assert "<details><summary>Stage log</summary>" in body and "- **boardmap** — draftling: +2 recipe(s) ⚠️ needs a human" in body
    assert "  - `data/recipes/m5stack-papers3__draftling`" in body
    assert body.index("### Proposed in this PR") < body.index("### Skipped this tick") < body.index("### Summary") < body.index("<details>")


def test_pr_body_with_nothing_proposed_says_so():
    body = report.render_pr_body(_r(memory={"expired": 2, "merged": 0, "rejected": 0, "removed": 0}))
    assert "Nothing new — memory reconciliation only" in body and "0 record(s) · 0 recipe(s)" in body and "- none" in body


def test_paths_are_deduplicated_across_stages_and_needs_human_aggregates():
    r = _r(stages=[{"name": "a", "paths": ["p1", "p2"], "needs_human": False},
                   {"name": "b", "paths": ["p2", "p3"], "needs_human": True}])
    assert r.paths == ["p1", "p2", "p3"] and r.needs_human


def test_pr_body_truncates_a_runaway_stage_summary():
    r = report.TickReport(when=NOW, stages=[{"name": "admit", "paths": [], "summary": "x" * 5000, "needs_human": False}])
    body = report.render_pr_body(r)
    assert "… (truncated" in body and len(body) < 2500
