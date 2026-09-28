"""EspAtlas Jr — pytest for the analytics-crossing module (jr/analytics_cross.py,
SPEC-analytics-cross.md). `build_funnel()` is pure and network-free: every test here runs
OFFLINE over committed fixtures shaped exactly like real GA4 RunReport / GSC
searchAnalytics.query responses (jr/fixtures/analytics_cross/*.json) for real esp-atlas
pages (minigotchi-esp32, area512, m5cardputer, m5stick-cplus2) and real queries.

The crux under test: the GSC-absolute-URL <-> GA4-pagePath join key normalization (trailing
slash, query string, percent-encoding), the None-vs-0 distinction between "axis unavailable"
and "axis loaded but this page had no row", and the two derived flags (striking_distance,
leak_flag) never firing off partial data.

Run: cd jr && python3 -m pytest tests/test_analytics_cross.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analytics_cross  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "analytics_cross"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _rows(name: str) -> list:
    return _load(name)["rows"]


@pytest.fixture
def ga_pages():
    return _rows("ga_pages.json")


@pytest.fixture
def ga_events():
    return _rows("ga_events.json")


@pytest.fixture
def gsc_pages():
    return _rows("gsc_pages.json")


@pytest.fixture
def gsc_queries():
    return _rows("gsc_queries.json")


def _row(table: dict, page: str) -> dict:
    for row in table["rows"]:
        if row["page"] == page:
            return row
    raise AssertionError(f"no row for page {page!r} in {[r['page'] for r in table['rows']]}")


# --- normalize_page: the join-key contract (SPEC §3) --------------------------------------


def test_normalize_page_strips_scheme_and_host():
    assert analytics_cross.normalize_page("https://esp-atlas.com/firmware/area512") == "/firmware/area512"


def test_normalize_page_strips_trailing_slash():
    assert analytics_cross.normalize_page("https://esp-atlas.com/firmware/minigotchi-esp32/") == "/firmware/minigotchi-esp32"
    assert analytics_cross.normalize_page("/firmware/minigotchi-esp32") == "/firmware/minigotchi-esp32"


def test_normalize_page_keeps_root_slash():
    assert analytics_cross.normalize_page("https://esp-atlas.com/") == "/"
    assert analytics_cross.normalize_page("/") == "/"


def test_normalize_page_strips_query_string():
    assert analytics_cross.normalize_page("https://esp-atlas.com/firmware/area512?ref=hn") == "/firmware/area512"


def test_normalize_page_strips_fragment():
    assert analytics_cross.normalize_page("https://esp-atlas.com/parts/m5cardputer#specs") == "/parts/m5cardputer"


def test_normalize_page_decodes_percent_encoding():
    assert analytics_cross.normalize_page("https://esp-atlas.com/parts/m5cardputer%2Dv2") == "/parts/m5cardputer-v2"


def test_normalize_page_preserves_case():
    assert analytics_cross.normalize_page("/parts/M5Cardputer") == "/parts/M5Cardputer"


def test_normalize_page_bare_ga4_pagepath_is_idempotent():
    assert analytics_cross.normalize_page("/parts/m5cardputer") == "/parts/m5cardputer"


# --- build_funnel: full join golden oracle (SPEC §2/§4/§5) ---------------------------------


def test_build_funnel_full_join_row_order_and_page_set(ga_pages, ga_events, gsc_pages, gsc_queries):
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    assert table["unavailable"] == []
    assert [r["page"] for r in table["rows"]] == [
        "/parts/m5cardputer",
        "/firmware/minigotchi-esp32",
        "/parts/m5stick-cplus2",
        "/parts/m5cardputer-v2",
        "/firmware/area512",
        "/firmware/ghost-firmware",
    ]
    assert table["generated_from"] == {"ga_pages": 5, "ga_events": 11, "gsc_pages": 5, "gsc_queries": 8}


def test_build_funnel_joins_ga_and_gsc_on_normalized_page(ga_pages, ga_events, gsc_pages, gsc_queries):
    """minigotchi-esp32: GSC row has a trailing slash the GA4 pagePath lacks -- must still join."""
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/firmware/minigotchi-esp32")
    assert row["page_views"] == 850
    assert row["active_users"] == 620
    assert row["sessions"] == 700
    assert row["part_view"] == 40
    assert row["flash_open"] == 5
    assert row["impressions"] == 1200
    assert row["clicks"] == 180
    assert row["ctr"] == pytest.approx(0.15)
    assert row["avg_position"] == pytest.approx(9.2)
    assert row["conv_view_to_part"] == pytest.approx(40 / 850)
    assert row["conv_part_to_flash"] == pytest.approx(5 / 40)
    assert [q["query"] for q in row["top_queries"]] == ["minigotchi esp32", "esp32 pwnagotchi alternative"]
    assert row["demand"] is None
    assert row["striking_distance"] is True  # "esp32 pwnagotchi alternative" @ pos 14.3
    assert row["leak_flag"] is True  # healthy demand+rank, conv_view_to_part ~0.047 < 0.05


def test_build_funnel_query_string_join(ga_pages, ga_events, gsc_pages, gsc_queries):
    """area512: GSC row carries ?ref=hn -- must strip it to join the bare GA4 pagePath."""
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/firmware/area512")
    assert row["page_views"] == 500
    assert row["impressions"] == 50
    assert row["avg_position"] == pytest.approx(25.4)
    assert row["conv_view_to_part"] == pytest.approx(120 / 500)
    assert row["striking_distance"] is False  # position 24.1 is outside the 8-20 band
    assert row["leak_flag"] is False  # avg_position > 20, not a healthy-rank page


def test_build_funnel_percent_encoded_join(ga_pages, ga_events, gsc_pages, gsc_queries):
    """m5cardputer-v2: GSC row is percent-encoded (%2D for '-') -- must decode to join."""
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/parts/m5cardputer-v2")
    assert row["page_views"] == 100
    assert row["part_view"] == 15
    assert row["flash_open"] == 0  # no flash_open row for this page -- real zero, not missing
    assert row["conv_part_to_flash"] == pytest.approx(0.0)  # part_view > 0, denominator valid
    assert row["impressions"] == 90
    assert row["striking_distance"] is True  # position 18.5 is in the 8-20 band


def test_build_funnel_clean_page_multiple_queries(ga_pages, ga_events, gsc_pages, gsc_queries):
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/parts/m5cardputer")
    assert row["page_views"] == 2000
    assert row["conv_view_to_part"] == pytest.approx(0.45)
    assert row["conv_part_to_flash"] == pytest.approx(300 / 900)
    assert [q["query"] for q in row["top_queries"]] == ["m5stack cardputer", "cardputer specs", "cardputer firmware list"]
    assert row["striking_distance"] is True  # "cardputer firmware list" @ pos 11.4
    assert row["leak_flag"] is False  # conversion is healthy (0.45)


def test_build_funnel_gsc_page_with_no_ga_match(ga_pages, ga_events, gsc_pages, gsc_queries):
    """m5stick-cplus2: ranks in GSC, GA4 page axis loaded but has no row for it -- real 0s, not None."""
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/parts/m5stick-cplus2")
    assert row["page_views"] == 0
    assert row["active_users"] == 0
    assert row["sessions"] == 0
    assert row["part_view"] == 0
    assert row["flash_open"] == 0
    assert row["conv_view_to_part"] is None  # page_views == 0 -- rate undefined, not fabricated
    assert row["conv_part_to_flash"] is None
    assert row["impressions"] == 400
    assert row["striking_distance"] is True  # "m5stickc plus2 review" @ pos 11.8
    assert row["leak_flag"] is False  # can't leak-flag without a real conversion rate


def test_build_funnel_ga_page_with_no_gsc_match(ga_pages, ga_events, gsc_pages, gsc_queries):
    """ghost-firmware: GA4 sees traffic, GSC page axis loaded but has no row -- real 0, ctr/position undefined."""
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries)
    row = _row(table, "/firmware/ghost-firmware")
    assert row["page_views"] == 30
    assert row["part_view"] == 0
    assert row["flash_open"] == 0
    assert row["conv_view_to_part"] == pytest.approx(0.0)  # page_views > 0, part_view real 0 -- valid rate
    assert row["conv_part_to_flash"] is None  # part_view == 0 -- undefined denominator
    assert row["impressions"] == 0
    assert row["clicks"] == 0
    assert row["ctr"] is None  # undefined at zero GSC rows, not a fabricated 0.0
    assert row["avg_position"] is None
    assert row["top_queries"] == []
    assert row["striking_distance"] is False
    assert row["leak_flag"] is False  # impressions 0 < the 10-impression health floor


# --- graceful degradation (SPEC §6) ---------------------------------------------------------


def test_build_funnel_missing_ga_pages_axis(ga_events, gsc_pages, gsc_queries):
    table = analytics_cross.build_funnel(None, ga_events, gsc_pages, gsc_queries)
    assert table["unavailable"] == ["ga_pages"]
    assert table["generated_from"]["ga_pages"] == 0
    for row in table["rows"]:
        assert row["page_views"] is None
        assert row["active_users"] is None
        assert row["sessions"] is None
        assert row["conv_view_to_part"] is None  # needs page_views
        assert row["leak_flag"] is False  # can't assert health without a conversion rate


def test_build_funnel_missing_ga_events_axis(ga_pages, gsc_pages, gsc_queries):
    table = analytics_cross.build_funnel(ga_pages, None, gsc_pages, gsc_queries)
    assert table["unavailable"] == ["ga_events"]
    for row in table["rows"]:
        assert row["part_view"] is None
        assert row["flash_open"] is None
        assert row["conv_view_to_part"] is None
        assert row["conv_part_to_flash"] is None


def test_build_funnel_missing_gsc_pages_axis(ga_pages, ga_events, gsc_queries):
    table = analytics_cross.build_funnel(ga_pages, ga_events, None, gsc_queries)
    assert table["unavailable"] == ["gsc_pages"]
    for row in table["rows"]:
        assert row["impressions"] is None
        assert row["clicks"] is None
        assert row["ctr"] is None
        assert row["avg_position"] is None
        assert row["leak_flag"] is False  # needs impressions/avg_position


def test_build_funnel_missing_gsc_queries_axis(ga_pages, ga_events, gsc_pages):
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, None)
    assert table["unavailable"] == ["gsc_queries"]
    for row in table["rows"]:
        assert row["top_queries"] == []
        assert row["striking_distance"] is False  # no queries to evaluate the band against


def test_build_funnel_all_axes_unavailable():
    table = analytics_cross.build_funnel(None, None, None, None)
    assert table["rows"] == []
    assert table["unavailable"] == ["ga_pages", "ga_events", "gsc_pages", "gsc_queries"]
    assert table["generated_from"] == {"ga_pages": 0, "ga_events": 0, "gsc_pages": 0, "gsc_queries": 0}


def test_build_funnel_never_raises_on_missing_axes(ga_pages, ga_events, gsc_pages, gsc_queries):
    # every single-axis-missing combination, plus all combinations of two -- none may raise.
    axes = [ga_pages, ga_events, gsc_pages, gsc_queries]
    for i in range(len(axes)):
        for j in range(len(axes)):
            trial = list(axes)
            trial[i] = None
            trial[j] = None
            analytics_cross.build_funnel(*trial)  # must not raise


def test_build_funnel_available_but_empty_axis_is_not_unavailable(ga_pages, gsc_pages, gsc_queries):
    """An axis that fetched successfully with zero rows is NOT the same as a failed fetch."""
    table = analytics_cross.build_funnel(ga_pages, [], gsc_pages, gsc_queries)
    assert table["unavailable"] == []
    row = _row(table, "/parts/m5cardputer")
    assert row["part_view"] == 0  # real zero: axis loaded, just no rows at all
    assert row["flash_open"] == 0


# --- duplicate-URL-variant merge on the GSC page axis (join-key correctness) ---------------


def test_build_funnel_merges_duplicate_gsc_page_variants_after_normalization():
    """Two GSC rows for URL variants that normalize to the same page must be summed, not
    silently dropped -- otherwise the normalization "fix" would itself lose GSC data."""
    ga_pages = [{"dimensionValues": [{"value": "/parts/dup-page"}], "metricValues": [{"value": "100"}, {"value": "80"}, {"value": "90"}]}]
    gsc_pages = [
        {"keys": ["https://esp-atlas.com/parts/dup-page/"], "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 10.0},
        {"keys": ["https://esp-atlas.com/parts/dup-page?ref=x"], "clicks": 5, "impressions": 50, "ctr": 0.1, "position": 20.0},
    ]
    table = analytics_cross.build_funnel(ga_pages, [], gsc_pages, [])
    row = _row(table, "/parts/dup-page")
    assert row["impressions"] == 150
    assert row["clicks"] == 15
    assert row["ctr"] == pytest.approx(15 / 150)
    assert row["avg_position"] == pytest.approx((10.0 * 100 + 20.0 * 50) / 150)


# --- flag boundaries (SPEC §5) ---------------------------------------------------------------


@pytest.mark.parametrize("position,expected", [(7.9, False), (8.0, True), (20.0, True), (20.1, False)])
def test_striking_distance_band_boundaries(position, expected):
    ga_pages = [{"dimensionValues": [{"value": "/parts/boundary"}], "metricValues": [{"value": "100"}, {"value": "80"}, {"value": "90"}]}]
    gsc_pages = [{"keys": ["https://esp-atlas.com/parts/boundary"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": position}]
    gsc_queries = [{"keys": ["boundary query", "https://esp-atlas.com/parts/boundary"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": position}]
    table = analytics_cross.build_funnel(ga_pages, [], gsc_pages, gsc_queries)
    row = _row(table, "/parts/boundary")
    assert row["striking_distance"] is expected


def test_striking_distance_ignores_zero_impression_queries():
    ga_pages = [{"dimensionValues": [{"value": "/parts/zero-imp"}], "metricValues": [{"value": "10"}, {"value": "8"}, {"value": "9"}]}]
    gsc_queries = [{"keys": ["ghost query", "https://esp-atlas.com/parts/zero-imp"], "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 12.0}]
    table = analytics_cross.build_funnel(ga_pages, [], [], gsc_queries)
    row = _row(table, "/parts/zero-imp")
    assert row["striking_distance"] is False


def test_leak_flag_requires_all_three_conditions():
    ga_pages = [{"dimensionValues": [{"value": "/parts/leaky"}], "metricValues": [{"value": "1000"}, {"value": "800"}, {"value": "900"}]}]
    ga_events = [{"dimensionValues": [{"value": "/parts/leaky"}, {"value": "part_view"}], "metricValues": [{"value": "10"}]}]
    gsc_pages = [{"keys": ["https://esp-atlas.com/parts/leaky"], "clicks": 100, "impressions": 500, "ctr": 0.2, "position": 5.0}]
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, [])
    row = _row(table, "/parts/leaky")
    assert row["conv_view_to_part"] == pytest.approx(0.01)
    assert row["leak_flag"] is True


def test_leak_flag_false_when_conversion_is_healthy():
    ga_pages = [{"dimensionValues": [{"value": "/parts/healthy"}], "metricValues": [{"value": "1000"}, {"value": "800"}, {"value": "900"}]}]
    ga_events = [{"dimensionValues": [{"value": "/parts/healthy"}, {"value": "part_view"}], "metricValues": [{"value": "200"}]}]
    gsc_pages = [{"keys": ["https://esp-atlas.com/parts/healthy"], "clicks": 100, "impressions": 500, "ctr": 0.2, "position": 5.0}]
    table = analytics_cross.build_funnel(ga_pages, ga_events, gsc_pages, [])
    row = _row(table, "/parts/healthy")
    assert row["leak_flag"] is False


# --- fetch layer: thin, reuses telemetry.py's Composio convention EXACTLY (SPEC §1) --------


def test_fetch_ga_pages_reuses_telemetry_convention():
    with patch.object(analytics_cross.telemetry, "_ex") as mock_ex:
        mock_ex.return_value = {"rows": [{"dimensionValues": [{"value": "/x"}], "metricValues": [{"value": "1"}, {"value": "1"}, {"value": "1"}]}]}
        rows = analytics_cross.fetch_ga_pages("2026-09-01", "2026-09-27")
        assert len(rows) == 1
        slug, kwargs = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
        assert slug == "GOOGLE_ANALYTICS_RUN_REPORT"
        assert kwargs["property"] == analytics_cross.telemetry.GA4_PROPERTY
        assert kwargs["dimensions"] == [{"name": "pagePath"}]
        assert {m["name"] for m in kwargs["metrics"]} == {"screenPageViews", "activeUsers", "sessions"}


def test_fetch_ga_events_requests_pagepath_and_eventname():
    with patch.object(analytics_cross.telemetry, "_ex") as mock_ex:
        mock_ex.return_value = {"rows": []}
        analytics_cross.fetch_ga_events("2026-09-01", "2026-09-27")
        slug, kwargs = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
        assert slug == "GOOGLE_ANALYTICS_RUN_REPORT"
        assert kwargs["dimensions"] == [{"name": "pagePath"}, {"name": "eventName"}]
        assert kwargs["metrics"] == [{"name": "eventCount"}]


def test_fetch_gsc_pages_uses_gsc_site_and_page_dimension():
    with patch.object(analytics_cross.telemetry, "_ex") as mock_ex:
        mock_ex.return_value = {"rows": []}
        analytics_cross.fetch_gsc_pages("2026-09-01", "2026-09-27")
        slug, kwargs = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
        assert slug == "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY"
        assert kwargs["siteUrl"] == analytics_cross.telemetry.GSC_SITE
        assert kwargs["dimensions"] == ["page"]


def test_fetch_gsc_queries_uses_query_and_page_dimensions():
    with patch.object(analytics_cross.telemetry, "_ex") as mock_ex:
        mock_ex.return_value = {"rows": []}
        analytics_cross.fetch_gsc_queries("2026-09-01", "2026-09-27")
        slug, kwargs = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
        assert slug == "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY"
        assert kwargs["dimensions"] == ["query", "page"]


@pytest.mark.parametrize("fetcher", ["fetch_ga_pages", "fetch_ga_events", "fetch_gsc_pages", "fetch_gsc_queries"])
def test_fetchers_propagate_none_on_failure(fetcher):
    with patch.object(analytics_cross.telemetry, "_ex", return_value=None):
        assert getattr(analytics_cross, fetcher)("2026-09-01", "2026-09-27") is None


@pytest.mark.parametrize("fetcher", ["fetch_ga_pages", "fetch_ga_events", "fetch_gsc_pages", "fetch_gsc_queries"])
def test_fetchers_return_empty_list_when_source_has_no_rows(fetcher):
    with patch.object(analytics_cross.telemetry, "_ex", return_value={}):
        assert getattr(analytics_cross, fetcher)("2026-09-01", "2026-09-27") == []


def test_weekly_funnel_orchestrates_all_four_fetchers_and_builds(ga_pages, ga_events, gsc_pages, gsc_queries):
    with patch.object(analytics_cross, "fetch_ga_pages", return_value=ga_pages), \
         patch.object(analytics_cross, "fetch_ga_events", return_value=ga_events), \
         patch.object(analytics_cross, "fetch_gsc_pages", return_value=gsc_pages), \
         patch.object(analytics_cross, "fetch_gsc_queries", return_value=gsc_queries):
        table = analytics_cross.weekly_funnel(days=7)
        assert table["unavailable"] == []
        assert len(table["rows"]) == 6
