"""Daily CLI -> resolver report -> ONE resolver reservation (class resolver); all sources injected."""
from __future__ import annotations

import json
from pathlib import Path

import demand_run
import research_work as rw
import resolver_run
from test_demand_broker import NOW, REAL_QUEUE, REAL_SNAPSHOT, SLUG, gh_remote, snapshot_miner, staged, without_unresolved
from test_demand_run import git_ok

SNAP = without_unresolved(REAL_SNAPSHOT)
ROW = {"vendor": "adafruit", "field": "download_mode", "missing": 20, "records": 26,
       "boards": ["adafruit-feather-esp32-s3", "adafruit-qtpy-esp32-c3", "adafruit-metro-esp32-s3"], "demand_impressions": 0, "ranks_poorly": 0}


def tree(root):
    board = root / "data/boards/vendor/example/board.md"
    board.parent.mkdir(parents=True)
    board.write_text('---\nid: example\nname: ES3C28P\n---\n')
    d = root / "docs/demand"
    d.mkdir(parents=True)
    (d / "research-queue.json").write_text(json.dumps(REAL_QUEUE, indent=1))
    return root


def resolver_updated(rows=(ROW,)):
    seen = {}
    def refresh(wt_path, *, now, snap=None):
        seen["snap"] = snap
        doc = {"version": 1, "date": now.date().isoformat(), "complete": True, "records": list(rows),
               "counts": {"vendors": 3, "gaps": len(rows), "boards_missing_total": sum(r["missing"] for r in rows)}}
        target = Path(wt_path) / resolver_run.STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc))
        return resolver_run.RefreshResult("updated", changed_paths=(resolver_run.STATE_PATH,), counts=doc["counts"])
    refresh.seen = seen
    return refresh


def resolver_deferred(wt_path, *, now, snap=None):
    return resolver_run.RefreshResult("deferred", error="controlled gauge failure")


def run(root, **kw):
    kw.setdefault("git", git_ok())
    kw.setdefault("gh", gh_remote())
    kw.setdefault("miner", snapshot_miner(SNAP))
    return demand_run.run(now=NOW, root=root, repo_slug=SLUG, python="/venv/bin/python", **kw)


def receipts(root):
    p = root / "docs/demand/work-receipts.json"
    return json.loads(p.read_text())["receipts"] if p.exists() else []


def test_a_ranked_gap_reserves_one_resolver_item_and_lands_the_report(tmp_path):
    root, git = tree(tmp_path), git_ok()
    refresh = resolver_updated()
    result = run(root, git=git, resolver_refresh=refresh)
    assert result.published and not result.aborted, result.line()
    paths = set(staged(git))
    assert resolver_run.STATE_PATH in paths and "docs/demand/work-receipts.json" in paths
    mine = [r for r in receipts(root) if r.get("source") == rw.SOURCE_RESOLVER]
    assert len(mine) == 1 and mine[0]["key"].startswith("resolver-") and mine[0]["resolver"]["vendor"] == "adafruit"
    assert mine[0]["term"] == "resolver adafruit download_mode"
    assert "resolvers updated: 1 vendor×field gap(s)" in result.line() and result.work.count("then") == 3
    assert refresh.seen["snap"] is not None and refresh.seen["snap"].get("date") == SNAP["date"]   # the day's snapshot orders ties


def test_a_deferred_gauge_never_blocks_the_rest(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git, resolver_refresh=resolver_deferred)
    assert result.published and not result.aborted
    assert resolver_run.STATE_PATH not in staged(git) and "resolvers deferred" in result.line()
    assert not [r for r in receipts(root) if r.get("source") == rw.SOURCE_RESOLVER]


def test_without_a_resolver_source_the_run_is_exactly_as_before(tmp_path):
    root, git = tree(tmp_path), git_ok()
    result = run(root, git=git)
    assert result.published and "resolvers" not in result.line() and resolver_run.STATE_PATH not in staged(git)
