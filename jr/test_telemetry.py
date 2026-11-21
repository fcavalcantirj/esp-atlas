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
    # aocr.org is both denylisted and (since 2026-11-18) a bouncing referral segment: still subtracted once
    assert telemetry._is_junk_segment(telemetry._channel_of("aocr.org"), 0.0, 0.0) is True
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
    assert breakdown[0]["dimensions"] == [{"name": "sessionSource"}, {"name": "city"},
                                          {"name": "sessionDefaultChannelGroup"},
                                          {"name": "screenResolution"}, {"name": "browser"}]
    assert breakdown[0]["limit"] == telemetry.GA4_SOURCE_ROW_LIMIT
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


def test_digest_states_the_undated_horizon_and_the_always_increasing_goal(monkeypatch, tmp_path):
    """Owner, 2026-11-10 (BIBLE-PLAN 'Growth goal'): 1,000,000 users is a horizon with no date; the
    operational goal is every completed 28-day window at or above the previous one."""
    calls = []
    message = _run_digest(monkeypatch, tmp_path, _fake_ex(calls))
    assert telemetry.GOAL_LINE in message
    assert "1,000,000 users" in telemetry.GOAL_LINE and "no date" in telemetry.GOAL_LINE
    assert "28d window" in telemetry.GOAL_LINE and "≥" in telemetry.GOAL_LINE
    assert "days left" not in message and " by 20" not in message
    assert not hasattr(telemetry, "TARGET_DATE")


# --- the junk rule judges every city × source segment, never a search or AI channel (2026-11-18) -----------
# Measured before the change (GA4, 2026-10-20..11-16): the Direct-only, whole-source rule removed 24 of 682
# sessions while Ashburn / Singapore / The Dalles / Council Bluffs / Beijing direct segments (0 engaged, avg
# under 2 s) stayed in, because the whole "(direct)" row averaged real users in. Splitting by city and
# applying the same thresholds to every non-search, non-AI segment removes 142 sessions with 0 engaged
# sessions inside them (two earlier windows: 143 / 2 engaged, 55 / 0).

def _seg(source, city, channel, sessions, engaged, avg_s):
    return {"dimensionValues": [{"value": source}, {"value": city}, {"value": channel}],
            "metricValues": [{"value": str(sessions)}, {"value": str(engaged)}, {"value": str(avg_s)}]}


def test_a_datacenter_direct_segment_is_junk_even_when_direct_overall_is_human():
    rows = [_seg("(direct)", "Ashburn", "Direct", 26, 0, 0.2),
            _seg("(direct)", "Rio de Janeiro", "Direct", 10, 8, 200.0),
            _seg("google", "Lisbon", "Organic Search", 25, 18, 95.0)]
    assert telemetry.spam_adjusted(61, rows, DENY) == {"sessions": 35, "engaged_sessions": 26}


def test_search_and_ai_channels_are_never_junk_even_when_they_bounce():
    rows = [_seg("google", "Gdynia", "Organic Search", 3, 0, 0.0),
            _seg("chatgpt.com", "(not set)", "AI Assistant", 2, 0, 2.4),
            _seg("bing", "Glenview", "Organic Search", 3, 0, 0.0)]
    assert telemetry.spam_adjusted(8, rows, DENY) == {"sessions": 8, "engaged_sessions": 0}
    for channel in ("Organic Search", "AI Assistant", "Paid Search", "Organic Social", "Email"):
        assert telemetry._is_junk_segment(channel, 0.0, 0.0) is False


def test_referral_and_unassigned_bounce_segments_are_junk():
    assert telemetry._is_junk_segment("Referral", 0.0, 0.0) is True
    assert telemetry._is_junk_segment("Unassigned", 3.0, 0.05) is True
    assert telemetry._is_junk_segment("Referral", 30.0, 0.05) is False        # slow: a person reading
    assert telemetry._is_junk_segment("Direct", 2.0, 0.5) is False            # engaged: a person


def test_the_breakdown_asks_for_source_city_channel_screen_and_browser():
    calls = []
    def fake(slug, args):
        calls.append(args)
        return {"rows": []}
    telemetry_ex = telemetry._ex
    try:
        telemetry._ex = fake
        assert telemetry._ga4_source_rows("2026-10-20", "2026-11-16") == []
    finally:
        telemetry._ex = telemetry_ex
    assert calls[0]["dimensions"] == [{"name": "sessionSource"}, {"name": "city"},
                                {"name": "sessionDefaultChannelGroup"},
                                {"name": "screenResolution"}, {"name": "browser"}]


# ═══════════════════ Bot rules aligned with deep-analytics (owner, 2026-11-20) ═══════════════════
#
# Beyond the denylist and the fast-unengaged rule, three behavioural rules from deep-analytics'
# bot_rules.py: (a) a sessionSource with >= 5 sessions and 0 engaged, (b) screen 800x600 with
# engagement <= 10%, (c) browser Android Webview with engagement <= 10%. Each rule judges the
# aggregate of its own group and claims every row in a matched group; (a)-(c) never count or remove
# Organic Search rows. The fast-unengaged rule keeps judging each source x city x channel segment.
# A row matched by several rules is removed once, attributed to the first rule in SPAM_RULE_KEYS.
# Fixtures are coding-domain traffic; slow durations keep the fast rule out of the new rules' tests.

def _full(source: str, sessions: float, engaged: float, avg_s: float, *, city: str = "Lisbon",
          channel: str | None = None, resolution: str = "1920x1080", browser: str = "Chrome") -> dict:
    """One row of the bot-rule breakdown: dimensions [sessionSource, city, sessionDefaultChannelGroup,
    screenResolution, browser], metrics [sessions, engagedSessions, averageSessionDuration]."""
    channel = channel or {"(direct)": "Direct", "google": "Organic Search"}.get(source, "Referral")
    return {"dimensionValues": [{"value": v} for v in (source, city, channel, resolution, browser)],
            "metricValues": [{"value": str(sessions)}, {"value": str(engaged)}, {"value": str(avg_s)}]}


def _removed(rows: list) -> dict:
    return telemetry.removed_by_rule(rows, DENY)


def test_rules_are_config_driven_module_constants():
    assert telemetry.ZERO_ENGAGED_MIN_SESSIONS == 5
    assert telemetry.JUNK_SCREEN_RESOLUTIONS == frozenset({"800x600"})
    assert telemetry.JUNK_BROWSERS == frozenset({"Android Webview"})
    assert telemetry.DEVICE_MAX_ENGAGEMENT_RATE == 0.10
    assert telemetry.RULES_EXEMPT_CHANNEL == "Organic Search"
    assert telemetry.SPAM_RULE_KEYS == ("fast_unengaged", "referral_denylist", "zero_engaged_source",
                                        "screen_resolution", "browser")


def test_removed_by_rule_reports_every_rule_even_when_nothing_matched():
    assert _removed([_full("github.com", 20, 15, 180.0)]) == {k: 0 for k in telemetry.SPAM_RULE_KEYS}


# --- (a) zero-engaged source -------------------------------------------------------------

def test_zero_engaged_source_with_five_sessions_is_removed():
    # a CI uptime checker hitting /firmware via a referrer: too slow for the fast rule, never engaged
    rows = [_full("ci-runner.buildkite.example", 5, 0, 40.0), _full("github.com", 20, 15, 180.0)]
    assert telemetry.spam_adjusted(25, rows, DENY) == {"sessions": 20, "engaged_sessions": 15}
    assert _removed(rows)["zero_engaged_source"] == 5


def test_zero_engaged_source_below_the_session_floor_is_kept():
    rows = [_full("lobste.rs", 4, 0, 40.0)]
    assert telemetry.spam_adjusted(4, rows, DENY) == {"sessions": 4, "engaged_sessions": 0}


def test_source_with_any_engaged_session_is_kept():
    rows = [_full("dev.to", 20, 1, 30.0)]
    assert telemetry.spam_adjusted(20, rows, DENY) == {"sessions": 20, "engaged_sessions": 1}


def test_zero_engaged_source_is_judged_over_all_its_rows():
    # 3 + 3 sessions from two cities: no single row reaches 5, the source does
    rows = [_full("pkg-mirror.example", 3, 0, 40.0, city="Ashburn"),
            _full("pkg-mirror.example", 3, 0, 40.0, city="Frankfurt"),
            _full("github.com", 10, 8, 200.0)]
    assert telemetry.spam_adjusted(16, rows, DENY) == {"sessions": 10, "engaged_sessions": 8}
    assert _removed(rows)["zero_engaged_source"] == 6


def test_zero_engaged_threshold_follows_the_module_constant(monkeypatch):
    monkeypatch.setattr(telemetry, "ZERO_ENGAGED_MIN_SESSIONS", 3)
    rows = [_full("lobste.rs", 3, 0, 40.0)]
    assert telemetry.spam_adjusted(3, rows, DENY) == {"sessions": 0, "engaged_sessions": 0}


# --- (b) junk screen resolution ----------------------------------------------------------

def test_800x600_with_low_engagement_is_removed_across_sources():
    # headless test browsers rendering the docs at the default 800x600: 2/20 engaged = 10%
    rows = [_full("github.com", 10, 1, 60.0, resolution="800x600"),
            _full("stackoverflow.com", 10, 1, 60.0, resolution="800x600"),
            _full("github.com", 30, 25, 200.0)]
    assert telemetry.spam_adjusted(50, rows, DENY) == {"sessions": 30, "engaged_sessions": 25}
    assert _removed(rows)["screen_resolution"] == 20


def test_800x600_with_engagement_above_the_ceiling_is_kept():
    rows = [_full("github.com", 10, 1, 60.0, resolution="800x600"),
            _full("stackoverflow.com", 10, 2, 60.0, resolution="800x600")]   # 3/20 = 15%
    assert telemetry.spam_adjusted(20, rows, DENY) == {"sessions": 20, "engaged_sessions": 3}


def test_the_screen_ceiling_follows_the_module_constant(monkeypatch):
    monkeypatch.setattr(telemetry, "DEVICE_MAX_ENGAGEMENT_RATE", 0.20)
    rows = [_full("github.com", 10, 1, 60.0, resolution="800x600"),
            _full("stackoverflow.com", 10, 2, 60.0, resolution="800x600")]   # 15% <= 20%
    assert telemetry.spam_adjusted(20, rows, DENY) == {"sessions": 0, "engaged_sessions": 0}


def test_other_resolutions_with_low_engagement_are_kept():
    rows = [_full("github.com", 10, 1, 60.0, resolution="1024x768", browser="Firefox")]
    assert telemetry.spam_adjusted(10, rows, DENY) == {"sessions": 10, "engaged_sessions": 1}


# --- (c) junk browser ----------------------------------------------------------------------

def test_android_webview_with_low_engagement_is_removed():
    # in-app link previews opening a firmware page: 1/12 engaged
    rows = [_full("t.co", 12, 1, 30.0, browser="Android Webview"),
            _full("github.com", 8, 6, 120.0, browser="Chrome")]
    assert telemetry.spam_adjusted(20, rows, DENY) == {"sessions": 8, "engaged_sessions": 6}
    assert _removed(rows)["browser"] == 12


def test_unlisted_browser_with_the_same_engagement_is_kept():
    rows = [_full("t.co", 12, 1, 30.0, browser="Samsung Internet")]
    assert telemetry.spam_adjusted(12, rows, DENY) == {"sessions": 12, "engaged_sessions": 1}


# --- channel scope ---------------------------------------------------------------------------

def test_organic_search_is_never_removed_by_the_new_rules():
    # a developer googling "esp32-c6 flash" on an 800x600 VM in an Android in-app browser
    rows = [_full("google", 9, 0, 40.0, resolution="800x600", browser="Android Webview")]
    assert telemetry.spam_adjusted(9, rows, DENY) == {"sessions": 9, "engaged_sessions": 0}


def test_organic_search_rows_do_not_shield_junk_in_other_channels():
    # engaged organic readers at 800x600 must not lift the headless Direct cluster over the ceiling
    rows = [_full("google", 10, 10, 300.0, resolution="800x600"),
            _full("(direct)", 10, 1, 60.0, resolution="800x600", browser="Firefox")]
    assert telemetry.spam_adjusted(20, rows, DENY) == {"sessions": 10, "engaged_sessions": 10}
    assert _removed(rows)["screen_resolution"] == 10


def test_new_rules_reach_human_arrival_channels_other_than_organic_search():
    # an AI-assistant citation preview fetched by a webview: protected from the fast rule only
    rows = [_full("chatgpt.com", 6, 0, 1.0, channel="AI Assistant", browser="Android Webview")]
    assert telemetry.spam_adjusted(6, rows, DENY) == {"sessions": 0, "engaged_sessions": 0}
    assert _removed(rows)["zero_engaged_source"] == 6


def test_fast_rule_still_protects_human_arrival_channels():
    rows = [_full("reddit.com", 3, 0, 1.0, channel="Organic Social")]
    assert telemetry.spam_adjusted(3, rows, DENY) == {"sessions": 3, "engaged_sessions": 0}


def test_fast_rule_still_judges_the_whole_source_city_segment():
    # one fast tab on a laptop screen inside a Rio developer's long direct reading: the segment is human
    rows = [_full("(direct)", 10, 8, 200.0, city="Rio de Janeiro"),
            _full("(direct)", 1, 0, 1.0, city="Rio de Janeiro", resolution="1366x768")]
    assert telemetry.spam_adjusted(11, rows, DENY) == {"sessions": 11, "engaged_sessions": 8}


# --- dedupe ------------------------------------------------------------------------------------

def test_row_matching_every_rule_is_removed_once_under_the_first_rule():
    rows = [_full("aocr.org", 10, 0, 0.5, resolution="800x600", browser="Android Webview"),
            _full("github.com", 20, 15, 180.0)]
    assert telemetry.spam_adjusted(30, rows, DENY) == {"sessions": 20, "engaged_sessions": 15}
    assert _removed(rows) == {"fast_unengaged": 10, "referral_denylist": 0, "zero_engaged_source": 0,
                              "screen_resolution": 0, "browser": 0}


def test_per_rule_removals_sum_to_the_excluded_sessions():
    rows = [_full("aocr.org", 9, 0, 40.0),
            _full("(direct)", 3, 0, 1.0),
            _full("ci-runner.buildkite.example", 6, 0, 40.0, resolution="800x600"),
            _full("stackoverflow.com", 10, 0, 60.0, resolution="800x600", browser="Android Webview"),
            _full("github.com", 30, 25, 200.0)]
    removed = _removed(rows)
    assert removed == {"fast_unengaged": 3, "referral_denylist": 9, "zero_engaged_source": 16,
                       "screen_resolution": 0, "browser": 0}
    assert sum(removed.values()) == 58 - telemetry.spam_adjusted(58, rows, DENY)["sessions"]


# --- the digest: per-rule line, 28d parity, truncation -------------------------------------------

def _rule_fake_ex(calls, by_window, row_count=None):
    """Like _fake_ex, with per-window breakdown rows and an optional GA4 rowCount."""
    def fake(slug, args):
        calls.append((slug, args))
        if slug == "GOOGLE_ANALYTICS_RUN_REPORT":
            r = args["dateRanges"][0]
            if args["dimensions"] == []:
                return {"rows": [{"metricValues": [{"value": "40"}, {"value": "60"}]}]}
            out = {"rows": by_window[(r["startDate"], r["endDate"])]}
            if row_count is not None:
                out["rowCount"] = row_count
            return out
        if args["dimensions"] == []:
            return {"rows": [{"clicks": 5, "impressions": 100, "position": 9.0}]}
        return {"rows": []}
    return fake


WEEK_ROWS = [_full("aocr.org", 9, 0, 40.0), _full("(direct)", 3, 0, 1.0),
             _full("ci-runner.buildkite.example", 6, 0, 40.0),
             _full("github.com", 12, 1, 60.0, resolution="800x600"),
             _full("t.co", 10, 0, 50.0, browser="Android Webview"),
             _full("github.com", 20, 16, 200.0)]
EVERY_WINDOW = {WINDOWS[7]: WEEK_ROWS, WINDOWS[28]: WEEK_ROWS, PRIOR_28: WEEK_ROWS}


def test_digest_names_how_many_sessions_each_rule_removed(monkeypatch, tmp_path):
    message = _run_digest(monkeypatch, tmp_path, _rule_fake_ex([], EVERY_WINDOW))
    assert "spam-adjusted 20 sessions / 16 engaged sessions" in message   # 60 - 40 removed
    rule_line = next(line for line in message.splitlines() if line.startswith("🧹"))
    assert "non-human channel ≤5s & ≤10% engaged: 3" in rule_line
    assert "referral denylist: 9" in rule_line
    assert "source ≥5 sessions & 0 engaged: 16" in rule_line      # ci-runner 6 + t.co 10
    assert "screen 800x600 ≤10% engaged: 12" in rule_line
    assert "browser Android Webview ≤10% engaged: 0" in rule_line  # t.co already claimed
    assert "counted once" in rule_line


def test_28d_deltas_apply_the_same_rules_to_both_windows(monkeypatch, tmp_path):
    current = [_full("github.com", 40, 30, 200.0),
               _full("t.co", 10, 1, 50.0, browser="Android Webview")]           # (c)
    prior = [_full("github.com", 30, 20, 200.0),
             _full("ci-runner.buildkite.example", 8, 0, 40.0),                   # (a)
             _full("stackoverflow.com", 20, 2, 60.0, resolution="800x600")]      # (b)
    by_window = {WINDOWS[7]: WEEK_ROWS, WINDOWS[28]: current, PRIOR_28: prior}
    message = _run_digest(monkeypatch, tmp_path, _rule_fake_ex([], by_window))
    assert "📈 28d adjusted engaged sessions: ↑ 30 vs 20 prior 28d" in message


def test_breakdown_at_the_row_limit_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(telemetry, "GA4_SOURCE_ROW_LIMIT", len(WEEK_ROWS))
    calls = []
    message = _run_digest(monkeypatch, tmp_path, _rule_fake_ex(calls, EVERY_WINDOW))
    assert "60 sessions · spam-adjusted unavailable" in message
    assert "📈 28d adjusted engaged sessions: unavailable" in message
    assert not any(line.startswith("🧹") for line in message.splitlines())
    assert all(a["limit"] == len(WEEK_ROWS) for s, a in calls
               if s == "GOOGLE_ANALYTICS_RUN_REPORT" and a["dimensions"])


def test_breakdown_whose_row_count_exceeds_the_returned_rows_fails_closed(monkeypatch, tmp_path):
    fake = _rule_fake_ex([], EVERY_WINDOW, row_count=len(WEEK_ROWS) + 1)
    message = _run_digest(monkeypatch, tmp_path, fake)
    assert "spam-adjusted unavailable" in message
    assert "📈 28d adjusted engaged sessions: unavailable" in message


def test_breakdown_with_a_matching_row_count_is_used(monkeypatch, tmp_path):
    fake = _rule_fake_ex([], EVERY_WINDOW, row_count=len(WEEK_ROWS))
    message = _run_digest(monkeypatch, tmp_path, fake)
    assert "spam-adjusted 20 sessions / 16 engaged sessions" in message
