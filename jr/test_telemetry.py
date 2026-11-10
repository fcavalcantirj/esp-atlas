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


# ═══════════════════ Raw vs spam-adjusted GA4 + the two 28-day growth deltas ═══════════════════
#
# The digest keeps the raw no-dimension distinct total and adds spam-adjusted sessions / engaged
# sessions computed from a second GA4 report broken down by sessionSource: raw minus rows whose
# source host is on the committed jr/referral_denylist.json, minus rows matching _is_junk_segment
# (source "(direct)" is the Direct channel). Fixtures use coding-domain sources only; no test
# touches the network -- every GA4/GSC call goes through a monkeypatched _ex.

import json  # noqa: E402

DENY = frozenset({"aocr.org"})


def _src(source: str, sessions: float, engaged: float, avg_duration_s: float) -> dict:
    """One GA4 runReport row for dimension [sessionSource] and metrics
    [sessions, engagedSessions, averageSessionDuration]."""
    return {"dimensionValues": [{"value": source}],
            "metricValues": [{"value": str(sessions)}, {"value": str(engaged)},
                             {"value": str(avg_duration_s)}]}


def _write(tmp_path, payload) -> "Path":
    p = tmp_path / "referral_denylist.json"
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return p


# --- the committed denylist + its fail-closed loader -------------------------------------

def test_committed_denylist_loads_and_names_the_aocr_referral_spam():
    hosts = telemetry.load_referral_denylist()
    assert hosts == frozenset({"aocr.org"})
    entry = json.loads(telemetry.REFERRAL_DENYLIST_PATH.read_text())[0]
    assert entry["added_on"] == "2026-11-10"
    assert "referral spam" in entry["reason"]


def test_loader_returns_every_valid_host(tmp_path):
    p = _write(tmp_path, [{"host": "aocr.org", "reason": "referral spam", "added_on": "2026-11-10"},
                          {"host": "spam.example", "reason": "bot referrer", "added_on": "2026-11-01"}])
    assert telemetry.load_referral_denylist(p) == frozenset({"aocr.org", "spam.example"})


@pytest.mark.parametrize("payload", [
    "not json at all",
    json.dumps({"host": "aocr.org", "reason": "spam", "added_on": "2026-11-10"}),  # not a list
    json.dumps(["aocr.org"]),                                                       # entry not an object
    json.dumps([{"reason": "spam", "added_on": "2026-11-10"}]),                     # host missing
    json.dumps([{"host": "", "reason": "spam", "added_on": "2026-11-10"}]),         # host empty
    json.dumps([{"host": "https://aocr.org/x", "reason": "spam", "added_on": "2026-11-10"}]),  # not a bare host
    json.dumps([{"host": "aocr.org", "added_on": "2026-11-10"}]),                   # reason missing
    json.dumps([{"host": "aocr.org", "reason": "  ", "added_on": "2026-11-10"}]),   # reason blank
    json.dumps([{"host": "aocr.org", "reason": "spam"}]),                           # added_on missing
    json.dumps([{"host": "aocr.org", "reason": "spam", "added_on": "11/10/2026"}]), # not ISO
    json.dumps([{"host": "aocr.org", "reason": "spam", "added_on": "2026-13-40"}]), # impossible date
    json.dumps([{"host": "aocr.org", "reason": "spam", "added_on": "20261110"}]),   # compact ISO refused
    json.dumps([{"host": "aocr.org", "reason": "spam", "added_on": "2026-11-10"},
                {"host": "aocr.org", "reason": "dup", "added_on": "2026-11-10"}]),  # duplicate host
])
def test_malformed_denylist_is_refused(tmp_path, payload):
    with pytest.raises(ValueError):
        telemetry.load_referral_denylist(_write(tmp_path, payload))


def test_missing_denylist_file_is_refused(tmp_path):
    with pytest.raises(ValueError):
        telemetry.load_referral_denylist(tmp_path / "absent.json")


# --- spam-adjusted sessions / engaged sessions -------------------------------------------

def test_denylisted_host_is_excluded():
    rows = [_src("aocr.org", 39, 0, 0.0), _src("github.com", 20, 15, 180.0)]
    assert telemetry.spam_adjusted(59, rows, DENY) == {"sessions": 20, "engaged_sessions": 15}


def test_denylisted_host_matches_its_subdomains_case_insensitively():
    rows = [_src("WWW.AOCR.ORG", 5, 1, 30.0), _src("github.com", 20, 15, 180.0)]
    assert telemetry.spam_adjusted(25, rows, DENY) == {"sessions": 20, "engaged_sessions": 15}


def test_lookalike_host_is_not_denylisted():
    rows = [_src("notaocr.org", 4, 3, 90.0)]
    assert telemetry.spam_adjusted(4, rows, DENY) == {"sessions": 4, "engaged_sessions": 3}


def test_behavioural_junk_is_excluded():
    # a CI script hitting /firmware with no referrer: (direct), 1s, 0 engaged
    rows = [_src("(direct)", 30, 0, 1.0), _src("stackoverflow.com", 8, 6, 140.0)]
    assert telemetry.spam_adjusted(38, rows, DENY) == {"sessions": 8, "engaged_sessions": 6}


def test_clean_sources_are_kept_including_engaged_direct():
    # a developer with a bookmarked build guide is (direct) but slow and engaged: human
    rows = [_src("(direct)", 10, 8, 200.0), _src("google", 25, 18, 95.0),
            _src("news.ycombinator.com", 6, 4, 60.0)]
    assert telemetry.spam_adjusted(41, rows, DENY) == {"sessions": 41, "engaged_sessions": 30}


def test_row_both_denylisted_and_junk_is_subtracted_once():
    rows = [_src("aocr.org", 39, 0, 0.0), _src("github.com", 20, 15, 180.0)]
    assert telemetry._is_junk_segment(telemetry._channel_of("aocr.org"), 0.0, 0.0) is False
    rows.append(_src("(direct)", 7, 0, 0.5))
    assert telemetry.spam_adjusted(66, rows, DENY) == {"sessions": 20, "engaged_sessions": 15}


def test_adjusted_sessions_never_go_negative():
    rows = [_src("aocr.org", 39, 0, 0.0)]
    assert telemetry.spam_adjusted(30, rows, DENY)["sessions"] == 0


# --- 28-day windows and delta lines -----------------------------------------------------

def test_prior_window_is_the_equal_length_window_just_before():
    S, E = telemetry.completed_window(28, telemetry.dt.date(2026, 11, 10))
    assert (S, E) == ("2026-10-12", "2026-11-08")
    assert telemetry.prior_window(S, E) == ("2026-09-14", "2026-10-11")


def test_delta_line_up():
    assert telemetry.delta_line("GSC clicks", 42, 30) == "📈 28d GSC clicks: ↑ 42 vs 30 prior 28d"


def test_delta_line_down():
    assert telemetry.delta_line("adjusted engaged sessions", 18, 25) == \
        "📈 28d adjusted engaged sessions: ↓ 18 vs 25 prior 28d"


def test_delta_line_equal():
    assert telemetry.delta_line("GSC clicks", 30, 30) == "📈 28d GSC clicks: → 30 vs 30 prior 28d"


def test_delta_line_unavailable_when_either_side_is_missing():
    assert telemetry.delta_line("GSC clicks", None, 30) == "📈 28d GSC clicks: unavailable"
    assert telemetry.delta_line("GSC clicks", 30, None) == "📈 28d GSC clicks: unavailable"


# --- the digest wiring (all network faked) -----------------------------------------------

WINDOWS = {7: ("2026-11-02", "2026-11-08"), 28: ("2026-10-12", "2026-11-08")}
PRIOR_28 = ("2026-09-14", "2026-10-11")


def _fake_ex(calls):
    by_window_ga4 = {
        WINDOWS[7]: [_src("aocr.org", 9, 0, 0.0), _src("(direct)", 3, 0, 1.0),
                     _src("github.com", 10, 7, 150.0)],
        WINDOWS[28]: [_src("aocr.org", 39, 0, 0.0), _src("google", 40, 30, 120.0)],
        PRIOR_28: [_src("google", 20, 12, 110.0)],
    }
    gsc_clicks = {WINDOWS[7]: 2, WINDOWS[28]: 9, PRIOR_28: 9}

    def fake(slug, args):
        calls.append((slug, args))
        if slug == "GOOGLE_ANALYTICS_RUN_REPORT":
            r = args["dateRanges"][0]
            window = (r["startDate"], r["endDate"])
            if args["dimensions"] == []:
                return {"rows": [{"metricValues": [{"value": "17"}, {"value": "22"}]}]}
            return {"rows": by_window_ga4[window]}
        window = (args["startDate"], args["endDate"])
        if args["dimensions"] == []:
            return {"rows": [{"clicks": gsc_clicks[window], "impressions": 100, "position": 9.0}]}
        return {"rows": []}
    return fake


def _run_digest(monkeypatch, tmp_path, fake):
    monkeypatch.setattr(telemetry, "completed_window", lambda days: WINDOWS[days])
    monkeypatch.setattr(telemetry, "__file__", str(tmp_path / "jr" / "telemetry.py"))
    monkeypatch.setattr(telemetry.notify, "send_telegram", lambda message: None)
    monkeypatch.setattr(telemetry, "_ex", fake)
    return telemetry.weekly_digest(7)


def test_digest_prints_raw_and_spam_adjusted_ga4(monkeypatch, tmp_path):
    calls = []
    message = _run_digest(monkeypatch, tmp_path, _fake_ex(calls))
    ga_line = next(line for line in message.splitlines() if "GA4" in line)
    assert "raw *17* distinct active users / 22 sessions" in ga_line
    assert "spam-adjusted 10 sessions / 7 engaged sessions" in ga_line   # 22 - 9 aocr - 3 junk
    breakdown = [a for s, a in calls if s == "GOOGLE_ANALYTICS_RUN_REPORT" and a["dimensions"]]
    assert breakdown[0]["dimensions"] == [{"name": "sessionSource"}]
    assert breakdown[0]["metrics"] == [{"name": "sessions"}, {"name": "engagedSessions"},
                                       {"name": "averageSessionDuration"}]


def test_digest_raw_request_is_unchanged(monkeypatch, tmp_path):
    calls = []
    _run_digest(monkeypatch, tmp_path, _fake_ex(calls))
    assert calls[0] == ("GOOGLE_ANALYTICS_RUN_REPORT", {
        "property": telemetry.GA4_PROPERTY,
        "dateRanges": [{"startDate": "2026-11-02", "endDate": "2026-11-08"}],
        "dimensions": [], "metrics": [{"name": "activeUsers"}, {"name": "sessions"}]})


def test_digest_prints_both_28d_growth_deltas(monkeypatch, tmp_path):
    calls = []
    message = _run_digest(monkeypatch, tmp_path, _fake_ex(calls))
    assert "📈 28d GSC clicks: → 9 vs 9 prior 28d" in message
    assert "📈 28d adjusted engaged sessions: ↑ 30 vs 12 prior 28d" in message
    gsc_windows = {(a["startDate"], a["endDate"]) for s, a in calls
                   if s == "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY" and a["dimensions"] == []}
    assert gsc_windows == {WINDOWS[7], WINDOWS[28], PRIOR_28}


def test_digest_marks_adjusted_unavailable_when_breakdown_fails(monkeypatch, tmp_path):
    calls = []
    real = _fake_ex(calls)

    def fake(slug, args):
        if slug == "GOOGLE_ANALYTICS_RUN_REPORT" and args["dimensions"]:
            return None
        return real(slug, args)
    message = _run_digest(monkeypatch, tmp_path, fake)
    assert "raw *17* distinct active users / 22 sessions · spam-adjusted unavailable" in message
    assert "📈 28d adjusted engaged sessions: unavailable" in message


def test_digest_fails_closed_on_a_malformed_denylist(monkeypatch, tmp_path):
    monkeypatch.setattr(telemetry, "REFERRAL_DENYLIST_PATH", _write(tmp_path, "[{\"host\": 1}]"))
    calls = []
    with pytest.raises(ValueError):
        _run_digest(monkeypatch, tmp_path, _fake_ex(calls))
    assert calls == []   # refused before any GA4/GSC call
