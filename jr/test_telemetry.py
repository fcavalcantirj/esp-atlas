"""Tests for jr/telemetry.py — guards against import-time Composio side effects.

jr-tests CI installs only "pyyaml jsonschema requests pytest" + apps/core -- no composio, no
~/.composio.key. `import telemetry` must succeed in that environment; only calling _ex() (which
routes through the real Google APIs) needs composio. This reproduces the CI environment by
blocking the composio import and reloading the module.
"""
from __future__ import annotations

import builtins
import importlib
import sys

import pytest


def test_import_succeeds_without_composio_installed(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "composio" or name.startswith("composio."):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.delitem(sys.modules, "composio", raising=False)
    monkeypatch.delitem(sys.modules, "telemetry", raising=False)

    telemetry = importlib.import_module("telemetry")
    try:
        assert telemetry.GA4_PROPERTY == "properties/551132215"
        assert telemetry.GSC_SITE == "sc-domain:esp-atlas.com"
    finally:
        importlib.reload(telemetry)  # restore the real module for later tests


def test_composio_client_not_built_until_first_ex_call(monkeypatch):
    import telemetry

    monkeypatch.setattr(telemetry, "_client", None)
    assert telemetry._client is None  # constructing telemetry never touches Composio


def test_composio_lazily_builds_and_caches_the_client(monkeypatch, tmp_path):
    import telemetry

    built = []

    class FakeComposio:
        def __init__(self, api_key):
            built.append(api_key)
            self.tools = self

        def execute(self, **kwargs):
            return {"successful": True, "data": kwargs}

    fake_module = type(sys)("composio")
    fake_module.Composio = FakeComposio
    monkeypatch.setitem(sys.modules, "composio", fake_module)
    (tmp_path / ".composio.key").write_text("fake-key\n")
    monkeypatch.setattr(telemetry.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(telemetry, "_client", None)

    client1 = telemetry._composio()
    client2 = telemetry._composio()

    assert built == ["fake-key"]           # constructed exactly once
    assert client1 is client2              # cached across calls


# ═══════════════════ GA4 segment diagnostic — never a distinct-user total ═══════════════════
#
# Mirrors the behavioral junk rule deep-analytics' bot_filter.py applies to esp-atlas GA4:
# a country x sessionDefaultChannelGroup segment is junk only when its channel is Direct AND
# its average session duration is <= 5.0s AND its engagement rate (engagedSessions/sessions)
# is <= 0.10. Country is never part of the rule -- a human running `curl` from any country can
# be Direct and fast, so only the behavioral triple gates exclusion.
#
# RED first: telemetry._is_junk_segment / telemetry._ga4_breakdown_totals do not exist yet.

import telemetry  # noqa: E402


def _row(country: str, channel: str, active_users: float, sessions: float,
         avg_duration_s: float, engaged_sessions: float) -> dict:
    """Build one GA4 runReport row in the shape GOOGLE_ANALYTICS_RUN_REPORT returns, for the
    breakdown dims [country, sessionDefaultChannelGroup] and metrics
    [activeUsers, sessions, averageSessionDuration, engagedSessions]."""
    return {
        "dimensionValues": [{"value": country}, {"value": channel}],
        "metricValues": [
            {"value": str(active_users)}, {"value": str(sessions)},
            {"value": str(avg_duration_s)}, {"value": str(engaged_sessions)},
        ],
    }


# --- junk predicate: all three conditions required --------------------------------------

def test_junk_predicate_true_when_direct_fast_and_unengaged():
    # a git-bisect script hitting the docs root with no referrer: Direct, 1s, 0 engaged
    assert telemetry._is_junk_segment("Direct", avg_duration_s=1.0, engagement_rate=0.0) is True


def test_junk_predicate_false_when_direct_but_engaged():
    # a developer pasting a firmware page URL straight into the address bar and reading it
    assert telemetry._is_junk_segment("Direct", avg_duration_s=2.0, engagement_rate=0.5) is False


def test_junk_predicate_false_when_direct_but_not_fast():
    # a developer with a bookmarked build-guide URL, Direct channel, but a long real session
    assert telemetry._is_junk_segment("Direct", avg_duration_s=120.0, engagement_rate=0.02) is False


def test_junk_predicate_false_when_fast_and_unengaged_but_not_direct():
    # a CI crawler arriving via Organic Search referrer: fast + unengaged, but channel != Direct
    assert telemetry._is_junk_segment("Organic Search", avg_duration_s=1.0, engagement_rate=0.0) is False


def test_junk_predicate_boundary_values_are_inclusive():
    # exactly at both ceilings (<=, not <) still counts as junk
    assert telemetry._is_junk_segment("Direct", avg_duration_s=5.0, engagement_rate=0.10) is True


# --- raw-vs-adjusted accumulation math ---------------------------------------------------

def test_raw_totals_sum_every_segment_regardless_of_junk():
    rows = [
        _row("United States", "Direct", 40, 40, 1.0, 0),         # junk: bot hammering /firmware
        _row("Brazil", "Organic Search", 12, 12, 240.0, 10),     # human reading a build guide
    ]
    totals = telemetry._ga4_breakdown_totals(rows)
    assert totals["raw"]["segment_user_memberships"] == 52
    assert totals["raw"]["sessions"] == 52


def test_adjusted_totals_exclude_only_junk_segments():
    rows = [
        _row("United States", "Direct", 40, 40, 1.0, 0),         # junk
        _row("Brazil", "Organic Search", 12, 12, 240.0, 10),     # human
        _row("Germany", "Direct", 3, 3, 300.0, 3),               # Direct but slow+engaged: human
    ]
    totals = telemetry._ga4_breakdown_totals(rows)
    assert totals["adjusted"]["segment_user_memberships"] == 15   # 12 (Brazil) + 3 (Germany)
    assert totals["adjusted"]["sessions"] == 15
    assert totals["raw"]["segment_user_memberships"] == 55
    assert totals["raw"]["sessions"] == 55


def test_adjusted_totals_equal_raw_when_no_segment_is_junk():
    rows = [_row("Brazil", "Organic Search", 12, 12, 240.0, 10)]
    totals = telemetry._ga4_breakdown_totals(rows)
    assert totals["adjusted"] == totals["raw"]


def test_adjusted_totals_are_zero_when_every_segment_is_junk():
    rows = [
        _row("United States", "Direct", 40, 40, 1.0, 0),
        _row("China", "Direct", 20, 20, 2.0, 1),   # engagement 1/20=0.05 <= 0.10: still junk
    ]
    totals = telemetry._ga4_breakdown_totals(rows)
    assert totals["adjusted"]["segment_user_memberships"] == 0
    assert totals["adjusted"]["sessions"] == 0
    assert totals["raw"]["segment_user_memberships"] == 60


def test_empty_rows_produce_zeroed_raw_and_adjusted_totals():
    totals = telemetry._ga4_breakdown_totals([])
    assert totals["raw"] == {"segment_user_memberships": 0.0, "sessions": 0.0}
    assert totals["adjusted"] == {"segment_user_memberships": 0.0, "sessions": 0.0}


# --- the weekly "Top search demand" list honours the miner's impression floor ----------------------

def test_top_search_demand_drops_rows_below_the_miners_impression_floor():
    import demand
    import telemetry
    rows = [{"keys": ["launcher esp32"], "impressions": 115, "position": 9.4},
            {"keys": ["bruce firmware cardputer"], "impressions": 1, "position": 4.0},
            {"keys": ["esp32 marauder flash"], "impressions": demand.MIN_IMPRESSIONS, "position": 18.2},
            {"keys": ["m5stick nemo ir"], "impressions": demand.MIN_IMPRESSIONS - 1, "position": 22.0},
            {"keys": ["esp32-c6 board"], "position": 31.0}]                  # no impressions at all
    got = telemetry.top_search_demand(rows)
    assert [r["keys"][0] for r in got] == ["launcher esp32", "esp32 marauder flash"]


def test_top_search_demand_caps_the_list_after_the_floor():
    import telemetry
    rows = [{"keys": [f"esp32-s3 board {i}"], "impressions": 1} for i in range(10)]
    rows += [{"keys": [f"firmware {i}"], "impressions": 50 + i} for i in range(8)]
    got = telemetry.top_search_demand(rows, n=6)
    assert len(got) == 6 and all(r["impressions"] >= 50 for r in got)


def test_the_floor_works_in_the_composio_venv_where_esp_atlas_core_is_not_installed(monkeypatch):
    # jr-telemetry runs this module under ~/.composio-venv with no PYTHONPATH: reaching for the
    # floor must never import demand.py -> tools.py -> esp_atlas_core
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name in ("demand", "tools") or name.startswith("esp_atlas_core"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    import telemetry
    monkeypatch.setattr(builtins, "__import__", blocked_import)
    got = telemetry.top_search_demand([{"keys": ["launcher esp32"], "impressions": 115},
                                       {"keys": ["bruce firmware"], "impressions": 1}])
    assert [r["keys"][0] for r in got] == ["launcher esp32"]


def test_the_miner_and_the_digest_share_one_floor():
    import demand
    import telemetry
    assert demand.MIN_IMPRESSIONS == telemetry.MIN_IMPRESSIONS == 10


def test_weekly_digest_uses_completed_dates_and_distinct_ga_total(monkeypatch, tmp_path):
    import datetime as dt
    import telemetry

    assert telemetry.completed_window(7, dt.date(2026, 11, 5)) == ("2026-10-28", "2026-11-03")
    monkeypatch.setattr(telemetry, "completed_window", lambda days: ("2026-10-28", "2026-11-03"))
    monkeypatch.setattr(telemetry, "__file__", str(tmp_path / "jr" / "telemetry.py"))
    monkeypatch.setattr(telemetry.notify, "send_telegram", lambda message: None)
    calls = []

    def fake_ex(slug, args):
        calls.append((slug, args))
        if slug == "GOOGLE_ANALYTICS_RUN_REPORT":
            return {"rows": [{"metricValues": [{"value": "8"}, {"value": "12"}]}]}
        if args["dimensions"] == []:
            return {"rows": [{"clicks": 2, "impressions": 10, "position": 9.0}]}
        return {"rows": []}

    monkeypatch.setattr(telemetry, "_ex", fake_ex)
    message = telemetry.weekly_digest(7)
    assert "2026-10-28→2026-11-03" in message
    assert "8* distinct active users / 12 sessions" in message
    assert calls[0][1]["dimensions"] == []
    assert calls[0][1]["dateRanges"] == [{"startDate": "2026-10-28", "endDate": "2026-11-03"}]


def test_weekly_digest_marks_failed_gsc_unavailable(monkeypatch, tmp_path):
    import telemetry

    monkeypatch.setattr(telemetry, "__file__", str(tmp_path / "jr" / "telemetry.py"))
    monkeypatch.setattr(telemetry.notify, "send_telegram", lambda message: None)
    monkeypatch.setattr(telemetry, "_ex", lambda slug, args: None)
    message = telemetry.weekly_digest(7)
    assert "GSC: unavailable" in message
    assert "GA4: unavailable" in message
