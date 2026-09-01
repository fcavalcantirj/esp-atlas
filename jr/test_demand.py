"""EspAtlas Jr — pytest for the read-only demand miner (jr/demand.py, SPEC-jr-demand-driven.md
Phase 1). Every test here runs OFFLINE — no network, no Composio — by construction: the only
network-touching function in demand.py is `_pull_live()`, which nothing below calls directly
(mine() calls it, and every mine() test monkeypatches it out).

Fixtures use REAL esp32-domain terms/ids/pairings (verified against this repo's actual
data/firmware/ and data/recipes/ at the time this test was written: `esp32marauder` exists and
has recipe `m5cardputer__esp32marauder`; `m5stick-nemo` exists and has recipe
`m5cardputer__m5stick-nemo` but NOT `m5stack-core2__m5stick-nemo`; `launcher` and `bruce` exist).
They are hardcoded here (not read live from the repo) so the tests stay stable/self-contained
regardless of future catalog changes.

Run: cd jr && python3 -m pytest test_demand.py -v
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand  # noqa: E402

FIRMWARE_IDS = {"esp32marauder", "launcher", "m5stick-nemo", "bruce", "tasmota"}
RECIPE_PAIRS = {"m5cardputer__esp32marauder", "m5cardputer__m5stick-nemo", "m5stack-core2__bruce"}
# real chip/part ids catalogued in THIS repo's data/socs/ at the time this test was written
# (verified: esp32-c6, esp32-s3 both exist and have a live /parts/<id> page); 'esp32-c9' is
# deliberately NOT included — no such Espressif chip exists, it's the UNCOVERED fixture below.
PART_IDS = {"esp32-c6", "esp32-s3", "esp32-c3", "esp32-h2"}


# ═══════════════════════════ normalize / weight — pure formula tests ═══════════════════════════

def test_normalize_term_lowercases_strips_collapses_whitespace():
    assert demand.normalize_term("  Marauder   Cardputer \n") == "marauder cardputer"
    assert demand.normalize_term(None) == ""


def test_position_penalty_worse_position_is_bigger_multiplier():
    assert demand.position_penalty(5) < demand.position_penalty(20)
    assert demand.position_penalty(None) == 1.0
    assert demand.position_penalty(9999) == demand.position_penalty(100)   # clamped


def test_gsc_weight_zero_impressions_is_zero():
    assert demand.gsc_weight(0, 0, None, None) == 0.0


def test_gsc_weight_high_impressions_low_ctr_bad_position_beats_low_impressions_good_position():
    poor = demand.gsc_weight(2000, 24, 0.012, 18.0)      # lots of impressions, barely clicked, buried
    good = demand.gsc_weight(2000, 400, 0.20, 3.0)        # same impressions, converts well, ranks well
    assert poor > good


def test_firstparty_weight_zero_result_weighted_higher_than_normal_hit():
    assert demand.firstparty_weight(10, zero_result=True) > demand.firstparty_weight(10, zero_result=False)
    assert demand.firstparty_weight(0, zero_result=True) == 0.0


# ═══════════════════════════ entity resolution ═══════════════════════════

def test_resolve_entity_board_and_firmware_token():
    r = demand.resolve_entity("marauder cardputer", FIRMWARE_IDS)
    assert r["board"] == "m5cardputer"
    assert r["chip"] == "esp32-s3"
    assert r["firmware_token"] == "esp32marauder"


def test_resolve_entity_bare_chip_only_no_board_no_firmware():
    r = demand.resolve_entity("esp32-c6", FIRMWARE_IDS)
    assert r["board"] is None
    assert r["chip"] == "esp32-c6"
    assert r["firmware_token"] is None
    assert r["part"] == "esp32-c6"


def test_resolve_entity_part_matches_spaced_chip_variant():
    """'esp32 c6' (no hyphen) must canonicalize to the SAME part id as 'esp32-c6' — the
    spacing/hyphen-variant blindness this fix closes."""
    r = demand.resolve_entity("esp32 c6", FIRMWARE_IDS)
    assert r["part"] == "esp32-c6"


def test_resolve_entity_part_none_when_no_chip_variant_shape_present():
    r = demand.resolve_entity("esp32 dev board", FIRMWARE_IDS)
    assert r["part"] is None


def test_dedup_key_merges_spacing_and_hyphen_chip_variants_into_one_part_key():
    hyphen = demand.resolve_entity("esp32-c6", FIRMWARE_IDS)
    spaced = demand.resolve_entity("esp32 c6", FIRMWARE_IDS)
    assert demand._dedup_key("esp32-c6", hyphen) == demand._dedup_key("esp32 c6", spaced)
    assert demand._dedup_key("esp32-c6", hyphen) == ("part", "esp32-c6")


def test_resolve_entity_capability_token():
    r = demand.resolve_entity("deauth attack cardputer", FIRMWARE_IDS)
    assert "wifi" in r["capability"]


def test_resolve_entity_fully_unresolved():
    r = demand.resolve_entity("esp32 tutorial pdf", FIRMWARE_IDS)
    assert r["board"] is None
    assert r["firmware_token"] is None
    # bare "esp32" still yields a generic chip signal — that's fine, classify_gap still UNRESOLVED
    assert r["chip"] == "esp32"


def test_esp32_stopword_never_false_matches_a_firmware_token():
    """A bare 'esp32' must never itself resolve to e.g. 'esp32marauder' — it's excluded as a
    stopword specifically to prevent this false-positive class."""
    r = demand.resolve_entity("esp32 dev board", FIRMWARE_IDS)
    assert r["firmware_token"] is None


def test_resolve_entity_no_chip_mention_at_all_is_none():
    r = demand.resolve_entity("bruce firmware", FIRMWARE_IDS)
    assert r["board"] is None
    assert r["chip"] is None
    assert r["firmware_token"] == "bruce"


def test_generic_board_fragment_does_not_false_match_a_hyphenated_firmware_id():
    """REGRESSION (caught running the miner live against real esp-atlas.com GSC data): 'm5
    stick s3' is a board query — it must NOT resolve firmware_token to 'm5stick-nemo' just
    because 'stick' is a substring of the fused id 'm5sticknemo'."""
    r = demand.resolve_entity("m5 stick s3", FIRMWARE_IDS)
    assert r["board"] == "m5stick-s3"
    assert r["firmware_token"] is None


def test_dedup_key_falls_back_to_board_when_no_firmware_token():
    """'cardputer firmware' names a board but no firmware ('firmware' is a stopword) — the
    dedup key must still be board-scoped (merge-worthy), even though gap ends up UNRESOLVED."""
    resolved = demand.resolve_entity("cardputer firmware", FIRMWARE_IDS)
    assert resolved["board"] == "m5cardputer"
    assert resolved["firmware_token"] is None
    assert demand._dedup_key("cardputer firmware", resolved) == ("board", "m5cardputer")


def test_gsc_weight_falls_back_to_computed_ctr_when_ctr_is_none():
    w_explicit = demand.gsc_weight(1000, 100, 0.1, 10.0)
    w_computed = demand.gsc_weight(1000, 100, None, 10.0)
    assert w_explicit == w_computed


# ═══════════════════════════ classify_gap — direct branch coverage, all four classes ═══════════════════════════

def test_classify_gap_unresolved_when_no_firmware_token():
    resolved = {"board": None, "chip": "esp32", "firmware_token": None, "capability": []}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, {"impressions": 500, "ctr": 0.01, "position": 20})
    assert gap == demand.GAP_UNRESOLVED


def test_classify_gap_uncovered_when_firmware_token_not_in_atlas():
    """Defensive branch: classify_gap's own contract, independent of whether resolve_entity's
    substring matcher can currently produce this input in the live pipeline."""
    resolved = {"board": None, "chip": None, "firmware_token": "nonexistent-fw", "capability": []}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, {"impressions": 500, "ctr": 0.01, "position": 20})
    assert gap == demand.GAP_UNCOVERED


def test_classify_gap_uncovered_when_board_pairing_missing():
    """Firmware IS catalogued, but not for this board — a populate/pairing gap (§6)."""
    resolved = {"board": "m5stack-core2", "chip": "esp32", "firmware_token": "m5stick-nemo", "capability": []}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, {"impressions": 80, "ctr": 0.01, "position": 22})
    assert gap == demand.GAP_UNCOVERED


def test_classify_gap_ranks_poorly_when_high_impression_low_ctr_bad_position():
    resolved = {"board": "m5cardputer", "chip": "esp32-s3", "firmware_token": "esp32marauder", "capability": []}
    metrics = {"impressions": 2100, "ctr": 0.0119, "position": 18.5}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics) == demand.GAP_RANKS_POORLY


def test_classify_gap_covered_ok_when_converts_fine():
    resolved = {"board": None, "chip": None, "firmware_token": "launcher", "capability": []}
    metrics = {"impressions": 300, "ctr": 0.15, "position": 4.2}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics) == demand.GAP_COVERED_OK


def test_classify_gap_covered_ok_when_no_gsc_metrics_at_all():
    """Firmware exists but we only have first-party (D2) volume, no D1 metrics — must default
    to COVERED_OK, never fabricate a RANKS_POORLY verdict without rank data."""
    resolved = {"board": None, "chip": None, "firmware_token": "bruce", "capability": []}
    metrics = {"impressions": 0, "ctr": None, "position": None}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics) == demand.GAP_COVERED_OK


# ═══════════════════ classify_gap — part/chip branch (the blindness fix) ═══════════════════

def test_classify_gap_part_ranks_poorly_when_high_impression_low_ctr_bad_position():
    """'esp32-c6' exists in the atlas but ranks badly for it — RANKS_POORLY, same D1 test as
    the firmware path, never UNRESOLVED just because entity resolution went via `part` not
    `firmware_token`."""
    resolved = {"board": None, "chip": "esp32-c6", "firmware_token": None, "capability": [],
               "part": "esp32-c6"}
    metrics = {"impressions": 700, "ctr": 0.0071, "position": 28.0}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS)
    assert gap == demand.GAP_RANKS_POORLY


def test_classify_gap_part_covered_ok_when_converts_fine():
    resolved = {"board": None, "chip": "esp32-s3", "firmware_token": None, "capability": [],
               "part": "esp32-s3"}
    metrics = {"impressions": 300, "ctr": 0.20, "position": 3.0}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS)
    assert gap == demand.GAP_COVERED_OK


def test_classify_gap_part_uncovered_when_not_in_atlas():
    """A plausible, shape-matched chip id ('esp32-c9') that isn't actually catalogued — a real
    populate gap, not a fabricated one (no chip list was hardcoded to produce this id, it's a
    structural esp32-<letter><digits> match)."""
    resolved = {"board": None, "chip": None, "firmware_token": None, "capability": [],
               "part": "esp32-c9"}
    metrics = {"impressions": 90, "ctr": 0.033, "position": 12.0}
    gap = demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics, PART_IDS)
    assert gap == demand.GAP_UNCOVERED


def test_classify_gap_part_ignored_without_part_ids_catalog_defaults_uncovered():
    """part_ids omitted (None) must never crash and never silently claim coverage — defaults to
    treating the part as not-yet-catalogued."""
    resolved = {"board": None, "chip": None, "firmware_token": None, "capability": [],
               "part": "esp32-c6"}
    metrics = {"impressions": 700, "ctr": 0.0071, "position": 28.0}
    assert demand.classify_gap(resolved, FIRMWARE_IDS, RECIPE_PAIRS, metrics) == demand.GAP_UNCOVERED


# ═══════════════════════════ build_demand_items — the full pure pipeline, offline fixtures ═══════════════════════════

D1_ROWS = [
    {"keys": ["marauder cardputer"], "impressions": 1840, "clicks": 22, "ctr": 0.0120, "position": 18.4},
    {"keys": ["cardputer marauder"], "impressions": 260, "clicks": 3, "ctr": 0.0115, "position": 19.1},
    {"keys": ["launcher esp32"], "impressions": 300, "clicks": 45, "ctr": 0.15, "position": 4.2},
    {"keys": ["nemo esp32"], "impressions": 200, "clicks": 40, "ctr": 0.20, "position": 5.0},
    # high-impression/low-CTR/weak-position chip demand, exists in the atlas -> RANKS_POORLY
    {"keys": ["esp32-c6"], "impressions": 700, "clicks": 5, "ctr": 0.0071, "position": 28.0},
    # same chip, spaced spelling -> must dedup-merge into the 'esp32-c6' item above
    {"keys": ["esp32 c6"], "impressions": 60, "clicks": 1, "ctr": 0.0167, "position": 30.0},
    # well-ranked existing chip -> COVERED_OK
    {"keys": ["esp32-s3"], "impressions": 300, "clicks": 60, "ctr": 0.20, "position": 3.0},
    # shape-matches a chip id, but 'esp32-c9' isn't an actual catalogued (or real) chip -> UNCOVERED
    {"keys": ["esp32-c9"], "impressions": 90, "clicks": 3, "ctr": 0.033, "position": 12.0},
    {"keys": ["nemo core2"], "impressions": 80, "clicks": 1, "ctr": 0.0125, "position": 22.0},
    {"keys": ["esp32 tutorial pdf"], "impressions": 60, "clicks": 30, "ctr": 0.5, "position": 3.0},
    {"keys": ["tiny query"], "impressions": 3, "clicks": 0, "ctr": 0.0, "position": 40.0},  # below MIN_IMPRESSIONS
]
D4_ROWS = [
    {"keys": ["launcher esp32", "https://esp-atlas.com/firmware/launcher"],
     "impressions": 250, "clicks": 40, "ctr": 0.16, "position": 4.0},
]


def _build(**kw):
    return demand.build_demand_items(
        D1_ROWS, kw.pop("d4", D4_ROWS), kw.pop("ga4", None),
        firmware_ids=FIRMWARE_IDS, recipe_pairs=RECIPE_PAIRS,
        part_ids=kw.pop("part_ids", PART_IDS),
        today="2026-08-31", **kw)


def test_floor_filter_drops_rows_below_min_impressions():
    items = _build()
    assert not any("tiny query" in it["raw_terms"] for it in items)


def test_dedup_merges_near_duplicate_terms_into_one_item_with_summed_volume():
    items = _build()
    marauder = [it for it in items if it["resolved"] and it["resolved"]["firmware_token"] == "esp32marauder"]
    assert len(marauder) == 1
    it = marauder[0]
    assert set(it["raw_terms"]) == {"marauder cardputer", "cardputer marauder"}
    assert it["impressions"] == 1840 + 260
    assert it["clicks"] == 22 + 3


def test_all_four_gap_classes_present_end_to_end():
    items = _build()
    gaps = {it["gap"] for it in items}
    assert gaps == {demand.GAP_UNCOVERED, demand.GAP_RANKS_POORLY, demand.GAP_COVERED_OK, demand.GAP_UNRESOLVED}


def test_marauder_cardputer_ranks_poorly_end_to_end():
    items = _build()
    it = next(it for it in items if it["resolved"] and it["resolved"]["firmware_token"] == "esp32marauder")
    assert it["gap"] == demand.GAP_RANKS_POORLY


def test_nemo_core2_is_uncovered_board_pairing_gap_end_to_end():
    items = _build()
    it = next(it for it in items if "nemo core2" in it["raw_terms"])
    assert it["gap"] == demand.GAP_UNCOVERED
    assert it["resolved"]["board"] == "m5stack-core2"
    assert it["resolved"]["firmware_token"] == "m5stick-nemo"


def test_launcher_and_nemo_esp32_are_covered_ok_end_to_end():
    items = _build()
    launcher = next(it for it in items if "launcher esp32" in it["raw_terms"])
    nemo = next(it for it in items if "nemo esp32" in it["raw_terms"])
    assert launcher["gap"] == demand.GAP_COVERED_OK
    assert nemo["gap"] == demand.GAP_COVERED_OK


def test_esp32_c6_ranks_poorly_end_to_end():
    """The blindness this fix closes: 'esp32-c6' — real top demand, exists in the atlas
    (has a live /parts/esp32-c6 page), weak position — used to fall to UNRESOLVED for having
    no `firmware_token`; must now classify by rank like firmware does."""
    items = _build()
    c6 = next(it for it in items if "esp32-c6" in it["raw_terms"])
    assert c6["resolved"]["part"] == "esp32-c6"
    assert c6["gap"] == demand.GAP_RANKS_POORLY


def test_esp32_c6_spacing_and_hyphen_variants_dedup_to_one_item_end_to_end():
    items = _build()
    matches = [it for it in items if it["resolved"] and it["resolved"].get("part") == "esp32-c6"]
    assert len(matches) == 1
    it = matches[0]
    assert set(it["raw_terms"]) == {"esp32-c6", "esp32 c6"}
    assert it["impressions"] == 700 + 60


def test_esp32_s3_covered_ok_end_to_end():
    """A well-ranked existing chip -> COVERED_OK, not a gap."""
    items = _build()
    s3 = next(it for it in items if "esp32-s3" in it["raw_terms"])
    assert s3["resolved"]["part"] == "esp32-s3"
    assert s3["gap"] == demand.GAP_COVERED_OK


def test_esp32_c9_uncovered_when_shape_matches_but_not_catalogued_end_to_end():
    """A plausible chip id, shape-matched, that isn't actually in the atlas -> UNCOVERED (a
    part worth adding), not UNRESOLVED and not a hardcoded chip-list lookup."""
    items = _build()
    c9 = next(it for it in items if "esp32-c9" in it["raw_terms"])
    assert c9["resolved"]["part"] == "esp32-c9"
    assert c9["gap"] == demand.GAP_UNCOVERED


def test_esp32_tutorial_pdf_is_genuinely_unresolved_end_to_end():
    """Free text with no board/firmware/chip-shape signal at all — still UNRESOLVED, per §4."""
    items = _build()
    tut = next(it for it in items if "esp32 tutorial pdf" in it["raw_terms"])
    assert tut["resolved"]["part"] is None
    assert tut["gap"] == demand.GAP_UNRESOLVED


def test_landing_page_attached_from_d4():
    items = _build()
    launcher = next(it for it in items if "launcher esp32" in it["raw_terms"])
    assert launcher["landing_page"] == "https://esp-atlas.com/firmware/launcher"


def test_items_ranked_by_weight_descending():
    items = _build()
    weights = [it["weight"] for it in items]
    assert weights == sorted(weights, reverse=True)


def test_demand_item_schema_shape():
    """Every item matches the §9 DemandItem field set exactly."""
    expected_fields = {"term", "raw_terms", "source", "impressions", "clicks", "ctr", "position",
                       "events", "zero_result", "weight", "resolved", "gap", "landing_page",
                       "first_seen", "last_seen"}
    items = _build()
    assert items
    for it in items:
        assert set(it.keys()) == expected_fields
        assert it["gap"] in {demand.GAP_UNCOVERED, demand.GAP_RANKS_POORLY,
                             demand.GAP_COVERED_OK, demand.GAP_UNRESOLVED}


# ═══════════════════════════ D2 (GA4 site-search) — the KNOWN ISSUE, and future-readiness ═══════════════════════════

def test_ga4_empty_searchterm_marks_d2_unavailable_and_never_crashes():
    empty_ga4 = [
        {"dimensionValues": [{"value": ""}], "metricValues": [{"value": "12"}]},
        {"dimensionValues": [{"value": "   "}], "metricValues": [{"value": "5"}]},
    ]
    parsed, d2_available = demand.parse_ga4_searchterm_rows(empty_ga4)
    assert parsed == []
    assert d2_available is False
    # and the full pipeline must still run clean on D1 alone
    items = _build(ga4=empty_ga4)
    assert items


def test_ga4_no_rows_at_all_marks_d2_unavailable():
    parsed, d2_available = demand.parse_ga4_searchterm_rows([])
    assert parsed == []
    assert d2_available is False


def test_ga4_working_searchterm_merges_into_matching_gsc_item():
    ga4 = [{"dimensionValues": [{"value": "marauder cardputer"}], "metricValues": [{"value": "37"}]}]
    items = _build(ga4=ga4)
    it = next(it for it in items if it["resolved"] and it["resolved"]["firmware_token"] == "esp32marauder")
    assert it["events"] == 37
    assert set(it["source"]) == {"gsc_query", "ga4_sitesearch"}


def test_ga4_zero_result_first_party_term_is_unresolved_but_weighted_by_zero_result():
    ga4 = [{"dimensionValues": [{"value": "evil portal esp32"}], "metricValues": [{"value": "9"}],
           "zero_result": True}]
    items = _build(ga4=ga4)
    it = next(it for it in items if "evil portal esp32" in it["raw_terms"])
    assert it["gap"] == demand.GAP_UNRESOLVED
    assert it["zero_result"] is True
    assert it["events"] == 9


def test_ga4_events_below_floor_are_dropped():
    ga4 = [{"dimensionValues": [{"value": "some rare thing"}], "metricValues": [{"value": "1"}]}]
    parsed, _ = demand.parse_ga4_searchterm_rows(ga4)
    filtered = demand._floor_filter_events(parsed)
    assert filtered == []


def test_ga4_malformed_metric_value_defaults_to_zero_events_not_a_crash():
    ga4 = [{"dimensionValues": [{"value": "marauder cardputer"}], "metricValues": [{"value": "not-a-number"}]}]
    parsed, available = demand.parse_ga4_searchterm_rows(ga4)
    assert parsed == [{"term": "marauder cardputer", "events": 0, "zero_result": False}]
    assert available is True


def test_parse_gsc_rows_skips_rows_with_no_keys_or_blank_query():
    rows = [{"impressions": 500}, {"keys": ["   "], "impressions": 500}]
    assert demand._parse_gsc_rows(rows, has_page=False) == []


def test_landing_pages_by_term_ignores_rows_with_no_page():
    rows = [{"term": "launcher esp32", "page": None, "impressions": 500}]
    assert demand._landing_pages_by_term(rows) == {}


# ═══════════════════════════ first_seen / last_seen carry-forward ═══════════════════════════

def test_first_seen_carries_forward_from_prior_snapshot():
    items = demand.build_demand_items(
        D1_ROWS, D4_ROWS, None, firmware_ids=FIRMWARE_IDS, recipe_pairs=RECIPE_PAIRS,
        today="2026-09-27", prior_first_seen={"launcher esp32": "2026-08-31"})
    launcher = next(it for it in items if "launcher esp32" in it["raw_terms"])
    assert launcher["first_seen"] == "2026-08-31"
    assert launcher["last_seen"] == "2026-09-27"


def test_first_seen_defaults_to_today_when_new():
    items = _build()
    launcher = next(it for it in items if "launcher esp32" in it["raw_terms"])
    assert launcher["first_seen"] == "2026-08-31"


# ═══════════════════════════ digest ═══════════════════════════

def test_digest_notes_d2_blind_when_unavailable():
    items = _build()
    digest = demand.build_digest(items, d2_available=False, window={"start": "2026-08-03", "end": "2026-08-31"})
    assert "D2 blind" in digest


def test_digest_notes_d2_live_when_available():
    items = _build()
    digest = demand.build_digest(items, d2_available=True, window={"start": "2026-08-03", "end": "2026-08-31"})
    assert "D2 live" in digest


def test_digest_lists_top_items_and_ranks_poorly_report():
    items = _build()
    digest = demand.build_digest(items, d2_available=False, window={"start": "2026-08-03", "end": "2026-08-31"})
    assert "Top demand" in digest
    assert "RANKS_POORLY" in digest
    assert "report for Felipe" in digest


def test_digest_never_has_a_bare_underscore_outside_a_code_span():
    """REGRESSION (caught sending a live digest to Telegram): a raw 'RANKS_POORLY'/'COVERED_OK'
    in the message text 400s Telegram's legacy Markdown (bare `_` = unmatched italic
    delimiter). Every gap label must be backtick-wrapped so the parser never looks at it."""
    items = _build()
    digest = demand.build_digest(items, d2_available=False, window={"start": "2026-08-03", "end": "2026-08-31"})
    for label in (demand.GAP_UNCOVERED, demand.GAP_RANKS_POORLY, demand.GAP_COVERED_OK, demand.GAP_UNRESOLVED):
        assert f"`{label}`" in digest or label not in digest


def test_digest_shows_event_counts_for_first_party_items():
    ga4 = [{"dimensionValues": [{"value": "marauder cardputer"}], "metricValues": [{"value": "37"}]}]
    items = _build(ga4=ga4)
    digest = demand.build_digest(items, d2_available=True, window={"start": "2026-08-03", "end": "2026-08-31"})
    assert "events 37" in digest


# ═══════════════════════════ snapshot / unresolved writers ═══════════════════════════

def test_write_snapshot_writes_git_trackable_json(tmp_path):
    items = _build()
    path = demand.write_snapshot(items, d2_available=False,
                                 window={"start": "2026-08-03", "end": "2026-08-31"},
                                 today="2026-08-31", demand_dir=tmp_path)
    assert path == tmp_path / "2026-08-31.json"
    data = json.loads(path.read_text())
    assert data["count"] == len(items)
    assert data["weight_formula_version"] == demand.WEIGHT_FORMULA_VERSION
    assert data["d2_available"] is False


def test_write_unresolved_only_contains_unresolved_items(tmp_path):
    items = _build()
    path = demand.write_unresolved(items, demand_dir=tmp_path)
    data = json.loads(path.read_text())
    assert all(it["gap"] == demand.GAP_UNRESOLVED for it in data["items"])
    assert data["count"] == len([it for it in items if it["gap"] == demand.GAP_UNRESOLVED])


def test_prior_first_seen_map_reads_latest_snapshot(tmp_path):
    demand.write_snapshot(_build(), False, {"start": "a", "end": "b"}, today="2026-08-31", demand_dir=tmp_path)
    prior_items = demand._latest_prior_snapshot(tmp_path)
    fs_map = demand._prior_first_seen_map(prior_items)
    assert fs_map.get("launcher esp32") == "2026-08-31"


def test_latest_prior_snapshot_empty_when_no_dir(tmp_path):
    assert demand._latest_prior_snapshot(tmp_path / "does-not-exist") == []


def test_latest_prior_snapshot_tolerates_corrupt_json(tmp_path):
    (tmp_path / "2026-08-24.json").write_text("{not valid json")
    assert demand._latest_prior_snapshot(tmp_path) == []


# ═══════════════════════════ mine() orchestration — READ-ONLY guarantee ═══════════════════════════

def test_mine_is_read_only_never_calls_authoring_or_pr_functions(tmp_path, monkeypatch):
    """Structural proof of the hard constraint: mine() must never touch scorer.py's authoring
    path or tools.py's PR/authoring functions, even indirectly."""
    def _forbidden(*a, **k):
        raise AssertionError("mine() must never author/PR anything (READ-ONLY, Phase 1)")

    monkeypatch.setattr(demand.tools, "author_firmware_record", _forbidden)
    monkeypatch.setattr(demand.tools, "open_pr", _forbidden)
    monkeypatch.setattr(demand.tools, "open_batch_pr", _forbidden)
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-08-03", "end": "2026-08-31"},
        "gsc_query_rows": D1_ROWS, "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": [],
    })
    sent = {}
    monkeypatch.setattr(demand.notify, "send_telegram", lambda text: sent.setdefault("text", text) or {"ok": True})

    result = demand.mine(send_telegram=True, demand_dir=tmp_path)
    assert result["items"]
    assert result["d2_available"] is False
    assert "text" in sent
    assert (tmp_path / "2026-08-31.json").exists() or any(tmp_path.glob("*.json"))


def test_mine_does_not_send_telegram_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-08-03", "end": "2026-08-31"},
        "gsc_query_rows": D1_ROWS, "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": [],
    })
    called = []
    monkeypatch.setattr(demand.notify, "send_telegram", lambda text: called.append(text))
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert called == []


# ═══════════════════════════ hard-constraint regression: never wired to jr-daily ═══════════════════════════

def test_module_never_imports_daily_authoring_entrypoints():
    src = (Path(__file__).resolve().parent / "demand.py").read_text()
    assert "import agent" not in src
    assert "import run\n" not in src
    assert "from agent" not in src
    assert "from run" not in src


def test_module_does_not_modify_scorer_or_maps():
    """demand.py may IMPORT the maps but must never write to scorer.py/device_map.py/
    capability_map.py (additive reuse only, per the task's hard constraint)."""
    src = (Path(__file__).resolve().parent / "demand.py").read_text()
    for forbidden in ("open(JR_DIR / \"scorer.py\"", "open(JR_DIR / \"device_map.py\"",
                      "open(JR_DIR / \"capability_map.py\""):
        assert forbidden not in src
