"""The demand miner resolves a bare model-number query to the ONE catalogued board it names
(demand work a721c3339f3d6348, SPEC-demand-work-consumer.md: GSC `fnk0104s` sat UNRESOLVED while
`freenove-fnk0104s` was catalogued and publicly searchable).

The rule is the research queue's existing vendor-prefix model key (jr/research_queue.py
`_model_matches`), reused — never a fuzzy matcher, no LLM, no network. Reads THIS repo's
data/ read-only; every board id below is real.

Run: python3 -m pytest jr/test_demand_model_board.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand  # noqa: E402
import research_queue as rq  # noqa: E402

FIRMWARE_IDS = {"esp32marauder", "launcher", "m5stick-nemo", "bruce"}
RECIPE_PAIRS = {"m5cardputer__esp32marauder"}
PART_IDS = {"esp32-s3", "esp32-c6"}
# the real GSC item from docs/demand/2026-11-06.json
FNK0104S_ROW = {"keys": ["fnk0104s"], "impressions": 22, "clicks": 1, "ctr": 0.0455, "position": 8.2}


@pytest.fixture(scope="module")
def catalog():
    return rq.load_catalog()


# ═══════════════════════════ research_queue.model_board — the reused rule ═══════════════════════════

@pytest.mark.parametrize("term, board", [
    ("fnk0104s", "freenove-fnk0104s"),
    ("FNK0104S", "freenove-fnk0104s"),
    ("fnk0104a", "freenove-fnk0104a"),
    ("fnk0104b", "freenove-fnk0104b"),
    ("fnk0104s datasheet", "freenove-fnk0104s"),
    ("fnk-0104s", "freenove-fnk0104s"),
])
def test_model_board_names_exactly_its_own_sku(catalog, term, board):
    assert rq.model_board(term, catalog) == (board, "fnk0104" + board[-1])


@pytest.mark.parametrize("term", [
    "fnk0104n",            # uncatalogued sibling
    "fnk0104",             # family stem, not a model key of any record
    "esp32", "s3", "esp32 s3",  # bare chips
    "esp32s3",             # a key two real records share (xiao-esp32s3, xiao-esp32s3-sense)
    "fnk0104a fnk0104b",   # names two boards — not exactly one
    "esp32 tutorial pdf",
    "",
])
def test_model_board_refuses_anything_but_one_named_board(catalog, term):
    assert rq.model_board(term, catalog) is None


def test_model_board_ignores_a_model_key_held_by_a_non_board_record():
    catalog = [{"id": "qx5000", "kind": "firmware", "title": "QX5000", "aliases": []}]
    assert rq.model_board("qx5000", catalog) is None


def test_model_board_is_the_research_queue_rule_for_a_single_term(catalog):
    """Same evidence the zero-result lane already records for the term — one rule, two callers."""
    _, evidence = rq.classify("fnk0104s", catalog)
    assert evidence["ids"] == [rq.model_board("fnk0104s", catalog)[0]]


# ═══════════════════════════ demand.resolve_entity ═══════════════════════════

def test_resolve_entity_resolves_bare_model_number_to_its_board(catalog):
    r = demand.resolve_entity("fnk0104s", FIRMWARE_IDS, catalog)
    assert r["board"] == "freenove-fnk0104s"
    assert r["board_model"] == "fnk0104s"
    assert r["chip"] == "esp32-s3"
    assert r["firmware_token"] is None
    assert r["part"] is None


@pytest.mark.parametrize("term", ["fnk0104a", "fnk0104b"])
def test_resolve_entity_siblings_never_resolve_to_fnk0104s(catalog, term):
    r = demand.resolve_entity(term, FIRMWARE_IDS, catalog)
    assert r["board"] == f"freenove-{term}"
    assert r["board"] != "freenove-fnk0104s"


@pytest.mark.parametrize("term", ["fnk0104n", "esp32", "s3", "esp32s3"])
def test_resolve_entity_no_board_for_unknown_shared_or_chip_terms(catalog, term):
    r = demand.resolve_entity(term, FIRMWARE_IDS, catalog)
    assert r["board"] is None
    assert r["board_model"] is None


def test_resolve_entity_device_map_keeps_precedence_and_has_no_board_model(catalog):
    r = demand.resolve_entity("cardputer firmware", FIRMWARE_IDS, catalog)
    assert r["board"] == "m5cardputer"
    assert r["board_model"] is None


def test_resolve_entity_without_catalog_is_unchanged():
    r = demand.resolve_entity("fnk0104s", FIRMWARE_IDS)
    assert r["board"] is None
    assert r["board_model"] is None


# ═══════════════════════════ demand.classify_gap — the board-model anchor ═══════════════════════════

def _model_resolved(**over):
    r = {"board": "freenove-fnk0104s", "board_model": "fnk0104s", "chip": "esp32-s3",
         "firmware_token": None, "capability": [], "part": None}
    r.update(over)
    return r


def test_classify_gap_board_model_anchor_covered_ok_for_the_real_item():
    metrics = {"impressions": 22, "ctr": 0.0455, "position": 8.2}
    gap = demand.classify_gap(_model_resolved(), FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS)
    assert gap == demand.GAP_COVERED_OK


def test_classify_gap_board_model_anchor_ranks_poorly_on_weak_metrics():
    metrics = {"impressions": 500, "ctr": 0.01, "position": 20.0}
    gap = demand.classify_gap(_model_resolved(), FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS)
    assert gap == demand.GAP_RANKS_POORLY


def test_classify_gap_device_map_board_only_stays_unresolved():
    resolved = _model_resolved(board="m5cardputer", board_model=None)
    metrics = {"impressions": 22, "ctr": 0.0455, "position": 8.2}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS) == demand.GAP_UNRESOLVED


def test_classify_gap_firmware_token_still_wins_over_board_model():
    resolved = _model_resolved(firmware_token="bruce")  # no freenove-fnk0104s__bruce recipe
    metrics = {"impressions": 22, "ctr": 0.0455, "position": 8.2}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS) == demand.GAP_UNCOVERED


def test_classify_gap_part_still_wins_over_board_model():
    resolved = _model_resolved(part="esp32-c9")  # uncatalogued part
    metrics = {"impressions": 22, "ctr": 0.0455, "position": 8.2}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS) == demand.GAP_UNCOVERED


# ═══════════════════════════ build_demand_items / mine — the full pipeline ═══════════════════════════

def _row(term, impressions=22):
    return {"keys": [term], "impressions": impressions, "clicks": 1, "ctr": 0.0455, "position": 8.2}


def _by_term(items):
    return {it["term"]: it for it in items}


def test_build_demand_items_fnk0104s_is_covered_ok_on_its_board(catalog):
    items = demand.build_demand_items([FNK0104S_ROW], firmware_ids=FIRMWARE_IDS, recipe_pairs=RECIPE_PAIRS,
                                      part_ids=PART_IDS, today="2026-11-06", catalog=catalog)
    (it,) = items
    assert it["resolved"]["board"] == "freenove-fnk0104s"
    assert it["gap"] == demand.GAP_COVERED_OK


def test_build_demand_items_keeps_siblings_distinct_and_unknown_unresolved(catalog):
    rows = [_row("fnk0104s"), _row("fnk0104a"), _row("fnk0104b"), _row("fnk0104n")]
    items = _by_term(demand.build_demand_items(rows, firmware_ids=FIRMWARE_IDS, recipe_pairs=RECIPE_PAIRS,
                                               part_ids=PART_IDS, today="2026-11-06", catalog=catalog))
    assert len(items) == 4
    for v in "sab":
        assert items[f"fnk0104{v}"]["resolved"]["board"] == f"freenove-fnk0104{v}"
        assert items[f"fnk0104{v}"]["gap"] == demand.GAP_COVERED_OK
    assert items["fnk0104n"]["resolved"] is None
    assert items["fnk0104n"]["gap"] == demand.GAP_UNRESOLVED


def test_mine_resolves_model_numbers_against_the_real_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-10-09", "end": "2026-11-05"},
        "gsc_query_rows": [FNK0104S_ROW], "gsc_query_page_rows": [], "ga4_searchterm_raw_rows": [],
        "trends": {},
    })
    result = demand.mine(send_telegram=False, demand_dir=tmp_path)
    (it,) = result["items"]
    assert it["resolved"]["board"] == "freenove-fnk0104s"
    assert it["gap"] == demand.GAP_COVERED_OK
