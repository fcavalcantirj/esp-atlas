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


# ═══════════════════ GA4 bot filter — honest raw-vs-human-adjusted totals ═══════════════════
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
    assert totals["raw"]["activeUsers"] == 52
    assert totals["raw"]["sessions"] == 52


def test_adjusted_totals_exclude_only_junk_segments():
    rows = [
        _row("United States", "Direct", 40, 40, 1.0, 0),         # junk
        _row("Brazil", "Organic Search", 12, 12, 240.0, 10),     # human
        _row("Germany", "Direct", 3, 3, 300.0, 3),               # Direct but slow+engaged: human
    ]
    totals = telemetry._ga4_breakdown_totals(rows)
    assert totals["adjusted"]["activeUsers"] == 15   # 12 (Brazil) + 3 (Germany)
    assert totals["adjusted"]["sessions"] == 15
    assert totals["raw"]["activeUsers"] == 55
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
    assert totals["adjusted"]["activeUsers"] == 0
    assert totals["adjusted"]["sessions"] == 0
    assert totals["raw"]["activeUsers"] == 60


def test_empty_rows_produce_zeroed_raw_and_adjusted_totals():
    totals = telemetry._ga4_breakdown_totals([])
    assert totals["raw"] == {"activeUsers": 0.0, "sessions": 0.0}
    assert totals["adjusted"] == {"activeUsers": 0.0, "sessions": 0.0}
