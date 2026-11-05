"""EspAtlas Jr — pytest for the demand miner's D2 lane (jr/demand.py): GA4 site search read from
`eventName` × `customEvent:q` (SPEC-jr-demand-driven.md §2, ⟨Q1⟩ amended 2026-11-04). Split out of
test_demand.py to keep both files under the size ceiling; shares its GSC fixtures. Fully OFFLINE —
`telemetry._ex` and `_pull_live` are monkeypatched wherever the network would be touched.

Run: cd jr && python3 -m pytest test_demand_ga4.py -v
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand  # noqa: E402
import demand_signal  # noqa: E402
from test_demand import D1_ROWS, D4_ROWS, _build  # noqa: E402


# ═══════════════════════════ D2 (GA4 site-search, eventName × customEvent:q) ═══════════════════════════

def _ga4_row(event_name, q, count):
    """One row in the exact live `GOOGLE_ANALYTICS_RUN_REPORT` shape for dims
    `[eventName, customEvent:q]` + metric `eventCount` (GA4 returns metric values as strings)."""
    return {"dimensionValues": [{"value": event_name}, {"value": q}], "metricValues": [{"value": str(count)}]}


# real terms from the live property (2026-11-04): waveshare came back on search_empty,
# Gps on search_results; "(not set)" is GA4's placeholder when the param is absent
GA4_LIVE_ROWS = [
    _ga4_row("search_submit", "waveshare", 2),
    _ga4_row("search_empty", "waveshare", 2),
    _ga4_row("search_submit", "Gps", 3),
    _ga4_row("search_submit", "  gps ", 1),
    _ga4_row("search_submit", "(not set)", 40),
    _ga4_row("search_empty", "(not set)", 7),
    _ga4_row("search_submit", "", 12),
]


def test_ga4_zero_result_term_is_flagged_and_counts_submits():
    parsed, _ = demand.parse_ga4_searchterm_rows(GA4_LIVE_ROWS)
    waveshare = next(r for r in parsed if r["term"] == "waveshare")
    assert waveshare == {"term": "waveshare", "events": 2, "zero_result": True}


def test_ga4_term_with_results_is_not_zero_result():
    parsed, _ = demand.parse_ga4_searchterm_rows(GA4_LIVE_ROWS)
    gps = next(r for r in parsed if r["term"] == "gps")
    assert gps["zero_result"] is False


def test_ga4_not_set_and_empty_terms_are_dropped():
    parsed, _ = demand.parse_ga4_searchterm_rows(GA4_LIVE_ROWS)
    assert {r["term"] for r in parsed} == {"waveshare", "gps"}


def test_ga4_case_and_whitespace_variants_merge_into_one_term():
    parsed, _ = demand.parse_ga4_searchterm_rows(GA4_LIVE_ROWS)
    gps = [r for r in parsed if r["term"] == "gps"]
    assert gps == [{"term": "gps", "events": 4, "zero_result": False}]


def test_ga4_one_real_term_marks_d2_available():
    _, d2_available = demand.parse_ga4_searchterm_rows(GA4_LIVE_ROWS)
    assert d2_available is True


def test_ga4_only_not_set_or_empty_terms_marks_d2_unavailable_and_never_crashes():
    blank_ga4 = [
        _ga4_row("search_submit", "(not set)", 40),
        _ga4_row("search_submit", "", 12),
        _ga4_row("search_empty", "   ", 5),
    ]
    parsed, d2_available = demand.parse_ga4_searchterm_rows(blank_ga4)
    assert parsed == []
    assert d2_available is False
    # and the full pipeline must still run clean on D1 alone
    items = _build(ga4=blank_ga4)
    assert items


def test_ga4_other_bucket_is_dropped_like_not_set():
    """GA4 folds high-cardinality values into "(other)" — an aggregate, never a typed term."""
    rows = [_ga4_row("search_submit", "(other)", 50), _ga4_row("search_empty", "(other)", 9)]
    assert demand.parse_ga4_searchterm_rows(rows) == ([], False)


def test_ga4_legacy_single_dimension_searchterm_rows_are_ignored():
    """The old `searchTerm`-only shape (one dimension value) can't carry an eventName — never
    misread it as a term."""
    legacy = [{"dimensionValues": [{"value": "marauder cardputer"}], "metricValues": [{"value": "37"}]}]
    assert demand.parse_ga4_searchterm_rows(legacy) == ([], False)


def test_ga4_other_event_names_are_ignored():
    rows = [_ga4_row("search_results", "gps", 9), _ga4_row("page_view", "gps", 99)]
    assert demand.parse_ga4_searchterm_rows(rows) == ([], False)


def test_ga4_no_rows_at_all_marks_d2_unavailable():
    parsed, d2_available = demand.parse_ga4_searchterm_rows([])
    assert parsed == []
    assert d2_available is False


def test_ga4_working_term_merges_into_matching_gsc_item():
    ga4 = [_ga4_row("search_submit", "Marauder Cardputer", 37)]
    items = _build(ga4=ga4)
    it = next(it for it in items if it["resolved"] and it["resolved"]["firmware_token"] == "esp32marauder")
    assert it["events"] == 37
    assert set(it["source"]) == {"gsc_query", "ga4_sitesearch"}


def test_ga4_zero_result_first_party_term_is_unresolved_but_weighted_by_zero_result():
    ga4 = [_ga4_row("search_submit", "Evil Portal ESP32", 9), _ga4_row("search_empty", "evil portal esp32", 9)]
    items = _build(ga4=ga4)
    it = next(it for it in items if "evil portal esp32" in it["raw_terms"])
    assert it["gap"] == demand.GAP_UNRESOLVED
    assert it["zero_result"] is True
    assert it["events"] == 9


def test_ga4_events_below_floor_are_dropped():
    parsed, _ = demand.parse_ga4_searchterm_rows([_ga4_row("search_submit", "some rare thing", 1)])
    filtered = demand._floor_filter_events(parsed)
    assert filtered == []


def test_ga4_malformed_metric_value_defaults_to_zero_events_not_a_crash():
    ga4 = [_ga4_row("search_submit", "marauder cardputer", "not-a-number")]
    parsed, available = demand.parse_ga4_searchterm_rows(ga4)
    assert parsed == [{"term": "marauder cardputer", "events": 0, "zero_result": False}]
    assert available is True


def test_pull_live_queries_ga4_event_name_by_customevent_q(monkeypatch):
    import telemetry
    seen = {}

    def fake_ex(slug, args):
        if slug == "GOOGLE_ANALYTICS_RUN_REPORT":
            seen["args"] = args
            return {"rows": GA4_LIVE_ROWS}
        return {"rows": []}

    monkeypatch.setattr(telemetry, "_ex", fake_ex)
    monkeypatch.setattr(demand.analytics_cross, "fetch_trends", lambda terms: {})
    live = demand._pull_live(days=7)
    args = seen["args"]
    assert args["dimensions"] == [{"name": "eventName"}, {"name": "customEvent:q"}]
    assert args["metrics"] == [{"name": "eventCount"}]
    assert args["dimensionFilter"] == {"filter": {
        "fieldName": "eventName", "inListFilter": {"values": ["search_submit", "search_empty"]}}}
    assert live["ga4_searchterm_raw_rows"] == GA4_LIVE_ROWS


def test_pull_live_flags_a_failed_ga4_call(monkeypatch):
    """`telemetry._ex` returns None when Composio reports failure — that must stay
    distinguishable from 'GA4 answered with no terms'."""
    import telemetry
    monkeypatch.setattr(telemetry, "_ex", lambda slug, args: None if slug == "GOOGLE_ANALYTICS_RUN_REPORT" else {"rows": []})
    monkeypatch.setattr(demand.analytics_cross, "fetch_trends", lambda terms: {})
    live = demand._pull_live(days=7)
    assert live["ga4_pull_ok"] is False
    assert live["ga4_searchterm_raw_rows"] == []


def test_pull_live_marks_an_answered_ga4_call_ok_even_with_no_rows(monkeypatch):
    import telemetry
    monkeypatch.setattr(telemetry, "_ex", lambda slug, args: {})
    monkeypatch.setattr(demand.analytics_cross, "fetch_trends", lambda terms: {})
    assert demand._pull_live(days=7)["ga4_pull_ok"] is True


def test_digest_says_ga4_pull_failed_instead_of_no_terms():
    items = _build()
    window = {"start": "2026-08-03", "end": "2026-08-31"}
    failed = demand.build_digest(items, d2_available=False, window=window, d2_pull_failed=True)
    empty = demand.build_digest(items, d2_available=False, window=window)
    assert "pull failed" in failed
    assert "no site-search terms" not in failed
    assert "no site-search terms" in empty


def test_mine_reports_failed_ga4_pull_in_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-08-03", "end": "2026-08-31"},
        "gsc_query_rows": D1_ROWS, "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": [],
        "ga4_pull_ok": False,
    })
    result = demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert result["d2_available"] is False
    assert "pull failed" in result["digest"]


def test_mine_d2_term_above_floor_reaches_the_snapshot(tmp_path, monkeypatch):
    ga4 = [_ga4_row("search_submit", "Waveshare", 6), _ga4_row("search_empty", "waveshare", 6)]
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-08-03", "end": "2026-08-31"},
        "gsc_query_rows": D1_ROWS, "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": ga4,
    })
    demand.mine(send_telegram=False, demand_dir=tmp_path)
    snapshot = json.loads(next(p for p in tmp_path.glob("*.json") if demand_signal.is_dated_snapshot(p)).read_text())
    waveshare = next(it for it in snapshot["items"] if it["term"] == "waveshare")
    assert waveshare["zero_result"] is True
    assert waveshare["events"] == 6
    assert "ga4_sitesearch" in waveshare["source"]


def test_mine_marks_d2_available_from_live_shaped_ga4_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "_pull_live", lambda days=demand.WINDOW_DAYS: {
        "window": {"start": "2026-08-03", "end": "2026-08-31"},
        "gsc_query_rows": D1_ROWS, "gsc_query_page_rows": D4_ROWS, "ga4_searchterm_raw_rows": GA4_LIVE_ROWS,
    })
    result = demand.mine(send_telegram=False, demand_dir=tmp_path)
    assert result["d2_available"] is True
    snapshot = json.loads(next(p for p in tmp_path.glob("*.json") if demand_signal.is_dated_snapshot(p)).read_text())
    assert snapshot["d2_available"] is True


def test_digest_shows_event_counts_for_first_party_items():
    ga4 = [_ga4_row("search_submit", "marauder cardputer", 37)]
    items = _build(ga4=ga4)
    digest = demand.build_digest(items, d2_available=True, window={"start": "2026-08-03", "end": "2026-08-31"})
    assert "events 37" in digest
