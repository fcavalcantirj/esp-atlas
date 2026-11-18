"""Daily CLI -> quote report -> ONE hygiene reservation (class hygiene); all sources injected."""
from __future__ import annotations

import json
from pathlib import Path

import demand_run
import quote_run
import research_work as rw
from test_demand_broker import NOW, REAL_QUEUE, REAL_SNAPSHOT, SLUG, gh_remote, snapshot_miner, staged, without_unresolved
from test_demand_run import git_ok

SNAP = without_unresolved(REAL_SNAPSHOT)
ROW = {"record": "data/boards/m5stack/m5dial/board.md", "id": "m5dial", "quotes": ["PORT.A | G13 | G15"],
       "urls": ["https://docs.m5stack.com/en/core/M5Dial"]}


def tree(root):
    board = root / "data/boards/vendor/example/board.md"
    board.parent.mkdir(parents=True)
    board.write_text('---\nid: example\nname: ES3C28P\n---\n')
    d = root / "docs/demand"
    d.mkdir(parents=True)
    (d / "research-queue.json").write_text(json.dumps(REAL_QUEUE, indent=1))
    return root


def quote_updated(rows=(ROW,), complete=True):
    def refresh(wt_path, *, now):
        doc = {"version": 1, "date": now.date().isoformat(), "complete": complete, "records": list(rows), "inconclusive": [],
               "counts": {"with_quotes": 87, "judged": 87, "fail": len(rows), "inconclusive": 0, "pages": 1, "pages_read": 1}}
        target = Path(wt_path) / quote_run.STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc))
        return quote_run.RefreshResult("updated", changed_paths=(quote_run.STATE_PATH,), counts=doc["counts"], complete=complete)
    return refresh


def quote_deferred(wt_path, *, now):
    return quote_run.RefreshResult("deferred", error="controlled quote source failure")


def run(root, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_remote())
    kw.setdefault("miner", snapshot_miner(SNAP))
    return demand_run.run(now=NOW, root=root, repo_slug=SLUG, python="/venv/bin/python", **kw)


def receipts(root):
    p = root / "docs/demand/work-receipts.json"
    return json.loads(p.read_text())["receipts"] if p.exists() else []


def test_a_complete_report_with_a_fail_row_reserves_one_hygiene_item_and_lands_the_report(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, quote_refresh=quote_updated())
    assert result.published and not result.aborted, result.line()
    paths = set(staged(git))
    assert quote_run.STATE_PATH in paths and "docs/demand/work-receipts.json" in paths
    mine = [r for r in receipts(root) if r.get("source") == rw.SOURCE_QUOTE]
    assert len(mine) == 1 and mine[0]["key"].startswith("fix-") and mine[0]["quote"]["record"] == ROW["record"]
    assert "quotes updated: 1 FAIL" in result.line() and "then" in result.work


def test_an_incomplete_report_lands_but_starts_no_hygiene_work(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, quote_refresh=quote_updated(complete=False))
    assert result.published and quote_run.STATE_PATH in staged(git)
    assert not [r for r in receipts(root) if r.get("source") == rw.SOURCE_QUOTE]
    assert "incomplete: no new hygiene work" in result.line()


def test_a_deferred_quote_source_never_blocks_the_rest(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, quote_refresh=quote_deferred)
    assert result.published and not result.aborted
    assert quote_run.STATE_PATH not in staged(git)
    assert "quotes deferred" in result.line() and "controlled quote source failure" in result.line()
    assert not [r for r in receipts(root) if r.get("source") == rw.SOURCE_QUOTE]


def test_without_a_quote_source_the_run_is_exactly_as_before(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git)
    assert result.published and "quotes" not in result.line() and quote_run.STATE_PATH not in staged(git)
