"""Tests for the research-queue wiring (SPEC-demand-research-queue.md): jr/demand.py's GA4 counts
and mine(), the dated-snapshot readers, and jr/demand_run.py landing docs/demand/research-queue.json.
Fully OFFLINE — `_pull_live` is monkeypatched, git/gh are recorders, the miner is a fake.

Run: cd jr && python3 -m pytest test_demand_research.py -v
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand  # noqa: E402
import demand_run  # noqa: E402
import demand_signal  # noqa: E402
import research_queue as rq  # noqa: E402
from test_demand import D1_ROWS, D4_ROWS  # noqa: E402
from test_demand_ga4 import _ga4_row  # noqa: E402
from test_demand_run import GSC_ROWS, TODAY, _items, _write_prev, fake_miner, norm_calls  # noqa: E402
from test_demand_run import gh_ok, git_ok, run as run_runner  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
WINDOW = {"start": "2026-08-03", "end": "2026-08-31"}


def _live(ga4):
    return lambda days=demand.WINDOW_DAYS: {"window": WINDOW, "gsc_query_rows": D1_ROWS,
                                            "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": ga4}


def _queue(demand_dir):
    return json.loads((demand_dir / "research-queue.json").read_text())["candidates"]


# ─────────────────────────── GA4 counts ───────────────────────────

def test_ga4_term_counts_keep_submits_and_empties_per_normalized_term():
    raw = [_ga4_row("search_submit", "ES3C28P", 1), _ga4_row("search_empty", "es3c28p ", 1),
           _ga4_row("search_submit", "gps", 2), _ga4_row("search_empty", "(not set)", 4)]
    assert demand.ga4_term_counts(raw) == [
        {"term": "es3c28p", "searches": 1, "zero_result_searches": 1},
        {"term": "gps", "searches": 2, "zero_result_searches": 0}]


def test_the_steering_parse_is_unchanged():
    raw = [_ga4_row("search_submit", "waveshare", 2), _ga4_row("search_empty", "waveshare", 2)]
    assert demand.parse_ga4_searchterm_rows(raw) == (
        [{"term": "waveshare", "events": 2, "zero_result": True}], True)


def test_min_events_steering_is_unchanged_for_a_single_zero_result_search():
    assert demand.MIN_EVENTS == 5
    ga4 = [_ga4_row("search_submit", "es3c28p", 1), _ga4_row("search_empty", "es3c28p", 1)]
    items = demand.build_demand_items(D1_ROWS, D4_ROWS, ga4, today=TODAY)
    assert not any(it["term"] == "es3c28p" for it in items)
    five = [_ga4_row("search_submit", "es3c28p", 5), _ga4_row("search_empty", "es3c28p", 5)]
    assert any(it["term"] == "es3c28p" for it in demand.build_demand_items(D1_ROWS, D4_ROWS, five, today=TODAY))


# ─────────────────────────── mine() ───────────────────────────

def test_mine_turns_one_zero_result_search_into_one_candidate(tmp_path, monkeypatch):
    ga4 = [_ga4_row("search_submit", "ES3C28P", 1), _ga4_row("search_empty", "ES3C28P", 1)]
    monkeypatch.setattr(demand, "_pull_live", _live(ga4))
    result = demand.mine(send_telegram=False, demand_dir=tmp_path)
    queue = _queue(tmp_path)
    assert list(queue) == ["es3c28p"]
    assert queue["es3c28p"]["classification"] == "missing_content"
    assert "research queue" in result["digest"] and "+1 new" in result["digest"]
    assert result["research"]["opened"] == ["es3c28p"]


def test_mine_creates_nothing_for_a_term_that_returned_results(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "_pull_live", _live([_ga4_row("search_submit", "gps", 1)]))
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert _queue(tmp_path) == {}


def test_mine_keeps_the_existing_queue_across_runs(tmp_path, monkeypatch):
    first = [_ga4_row("search_submit", "es3c28p", 1), _ga4_row("search_empty", "es3c28p", 1)]
    monkeypatch.setattr(demand, "_pull_live", _live(first))
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    second = [_ga4_row("search_submit", "lilygo-t-bea", 1), _ga4_row("search_empty", "lilygo-t-bea", 1)]
    monkeypatch.setattr(demand, "_pull_live", _live(second))
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    queue = _queue(tmp_path)
    assert set(queue) == {"es3c28p", "lilygo t bea"}
    assert queue["lilygo t bea"]["classification"] == "alias_typo"


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(root)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def test_mine_writes_nothing_under_data(tmp_path, monkeypatch):
    ga4 = [_ga4_row("search_submit", t, 1) for t in ("es3c28p", "lilygo-t-bea", "lilygo-t-beam")]
    ga4 += [_ga4_row("search_empty", t, 1) for t in ("es3c28p", "lilygo-t-bea", "lilygo-t-beam")]
    monkeypatch.setattr(demand, "_pull_live", _live(ga4))
    before = _tree_digest(REPO / "data")
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert _tree_digest(REPO / "data") == before
    assert (tmp_path / "research-queue.json").exists()


def test_the_queue_refuses_to_write_under_data(tmp_path):
    with pytest.raises(ValueError, match="data/"):
        rq.write_queue(rq.empty_queue(), REPO / "data" / "research-queue.json")


# ─────────────────────────── dated-snapshot readers ignore the queue ───────────────────────────

def _seed(demand_dir: Path):
    _write_prev(demand_dir.parent.parent, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    queue, _ = rq.update_queue(rq.empty_queue(), [{"term": "es3c28p", "searches": 1,
                                                   "zero_result_searches": 1}], [], TODAY)
    rq.write_queue(queue, demand_dir / rq.QUEUE_NAME)


def test_the_steer_loader_never_reads_the_queue_as_a_snapshot(tmp_path):
    d = tmp_path / "docs" / "demand"
    _seed(d)
    assert demand_signal.load_latest(d, TODAY)["date"] == "2026-11-02"


def test_the_runner_never_reads_the_queue_as_a_snapshot(tmp_path):
    d = tmp_path / "docs" / "demand"
    _seed(d)
    assert demand_run._read_latest(d)["date"] == "2026-11-02"


def test_the_miner_carries_first_seen_from_the_snapshot_not_the_queue(tmp_path):
    d = tmp_path / "docs" / "demand"
    _seed(d)
    snapshot_items = json.loads((d / "2026-11-02.json").read_text())["items"]
    assert demand._latest_prior_snapshot(d) == snapshot_items != []


# ─────────────────────────── the daily runner lands the queue ───────────────────────────

def queue_miner(terms, today=TODAY):
    """fake_miner + the queue the real miner writes beside the snapshot."""
    base = fake_miner(today=today)

    def miner(wt_path: Path, *, python: str, telegram: bool):
        p = base(wt_path, python=python, telegram=telegram)
        path = wt_path / "docs" / "demand" / rq.QUEUE_NAME
        rows = [{"term": t, "searches": 1, "zero_result_searches": 1} for t in terms]
        queue, _ = rq.update_queue(rq.load_queue(path), rows, [], today)
        rq.write_queue(queue, path)
        return p

    return miner


def test_the_runner_stages_the_research_queue_with_the_snapshot(tmp_path):
    git = git_ok()
    res = run_runner(tmp_path, git=git, miner=queue_miner(["es3c28p"]))
    assert res.published is True
    staged = next(c for c in norm_calls(git) if c[:1] == ("add",))[2:]
    assert "docs/demand/research-queue.json" in staged
    assert not any(p.startswith("data/") for p in staged)


def test_an_unchanged_snapshot_with_a_changed_queue_still_lands(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    gh = gh_ok()
    res = run_runner(tmp_path, gh=gh, miner=queue_miner(["es3c28p"]))
    assert res.published is True
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert "research queue changed (no-op: demand unchanged" in create[create.index("--body") + 1]


def test_an_unchanged_snapshot_and_queue_is_still_a_noop(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    d = tmp_path / "docs" / "demand"
    rq.write_queue(rq.empty_queue(), d / rq.QUEUE_NAME)
    res = run_runner(tmp_path, miner=queue_miner([]))
    assert res.published is False and res.reason.startswith("no-op")


def test_a_queue_change_in_last_seen_only_is_still_a_noop(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    d = tmp_path / "docs" / "demand"
    queue, _ = rq.update_queue(rq.empty_queue(), [{"term": "es3c28p", "searches": 1,
                                                   "zero_result_searches": 1}], [], "2026-11-02")
    rq.write_queue(queue, d / rq.QUEUE_NAME)
    res = run_runner(tmp_path, miner=queue_miner(["es3c28p"]))     # refreshes last_seen to TODAY
    assert json.loads((d / rq.QUEUE_NAME).read_text())["candidates"]["es3c28p"]["last_seen"] == TODAY
    assert res.published is False and res.reason.startswith("no-op")


def test_a_miner_without_a_queue_file_lands_the_two_snapshot_paths_only(tmp_path):
    git = git_ok()
    res = run_runner(tmp_path, git=git)
    assert res.published is True
    staged = next(c for c in norm_calls(git) if c[:1] == ("add",))[2:]
    assert "docs/demand/research-queue.json" not in staged


def test_the_pr_body_carries_the_research_queue_line(tmp_path):
    gh = gh_ok()
    run_runner(tmp_path, gh=gh, miner=queue_miner(["es3c28p"]))
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    body = create[create.index("--body") + 1]
    assert "research queue" in body and "1 open" in body


# ─────────────────────────── checker findings (2026-11-04) ───────────────────────────

def test_a_broken_research_queue_never_blocks_the_demand_snapshot(tmp_path, monkeypatch):
    (tmp_path / rq.QUEUE_NAME).write_text("{not json")
    ga4 = [_ga4_row("search_submit", "es3c28p", 1), _ga4_row("search_empty", "es3c28p", 1)]
    monkeypatch.setattr(demand, "_pull_live", _live(ga4))
    result = demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert any(demand_signal.is_dated_snapshot(p) for p in tmp_path.iterdir())
    assert (tmp_path / rq.QUEUE_NAME).read_text() == "{not json"      # human triage never reset
    assert "research queue NOT updated" in result["digest"] and result["research"]["error"]


def test_a_growing_catalog_alone_does_not_land_a_queue_change(tmp_path):
    _write_prev(tmp_path, "2026-11-02", _items(GSC_ROWS, "2026-11-02"))
    d = tmp_path / "docs" / "demand"
    row_ = [{"term": "es3c28p", "searches": 1, "zero_result_searches": 1}]
    queue, _ = rq.update_queue(rq.empty_queue(), row_, [], "2026-11-02")
    rq.write_queue(queue, d / rq.QUEUE_NAME)
    grown = [{"id": "zzzz9", "kind": "board", "title": "", "aliases": []}]

    def miner(wt_path, *, python, telegram):
        p = fake_miner()(wt_path, python=python, telegram=telegram)
        path = wt_path / "docs" / "demand" / rq.QUEUE_NAME
        rq.write_queue(rq.update_queue(rq.load_queue(path), row_, grown, TODAY)[0], path)
        return p

    res = run_runner(tmp_path, miner=miner)
    assert json.loads((d / rq.QUEUE_NAME).read_text())["candidates"]["es3c28p"]["evidence"]["checked"] == 1
    assert res.published is False and res.reason.startswith("no-op")


def test_the_pr_body_counts_a_reopened_candidate(tmp_path):
    d = tmp_path / "docs" / "demand"
    row_ = [{"term": "es3c28p", "searches": 1, "zero_result_searches": 1}]
    queue, _ = rq.update_queue(rq.empty_queue(), row_, [], "2026-09-01")
    rq.close(queue, "es3c28p", "done", "2026-09-01")
    rq.write_queue(queue, d / rq.QUEUE_NAME)
    gh = gh_ok()
    run_runner(tmp_path, gh=gh, miner=queue_miner(["es3c28p"]))
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert "1 reopened" in create[create.index("--body") + 1]
