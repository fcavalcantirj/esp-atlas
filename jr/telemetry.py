"""EspAtlas Jr — weekly growth telemetry (§3d).

Pulls GA4 + Search Console for esp-atlas.com via **Composio OAuth** (no service-account key),
sends a weekly digest to Telegram, and writes a git-tracked snapshot. GSC top-demand queries
are surfaced as Jr's data-priority signal. Run with the composio venv:

    ~/.composio-venv/bin/python telemetry.py
"""
from __future__ import annotations
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify  # stdlib-only

ENTITY = "7UQIn73xcXnpKIQiaTJzjrCRZk0VznPv"
GA4_PROPERTY = "properties/551132215"
GSC_SITE = "sc-domain:esp-atlas.com"
GOAL_LINE = ("🎯 1,000,000 users is the horizon (no date) · goal: every completed 28d window ≥ the previous "
             "one on GSC clicks and adjusted engaged sessions")   # owner, 2026-11-10 (BIBLE-PLAN)
# GSC query floor — rows below it are statistically thin (SPEC-jr-demand-driven.md §3.3). Lives
# HERE, stdlib-only, because jr-telemetry runs this module in the composio venv where demand.py's
# `tools` -> esp_atlas_core import cannot load; demand.py re-exports this one value.
MIN_IMPRESSIONS = 10
_client = None


def _composio():
    """Lazily import composio, read the OAuth key, and build+cache the client.

    Deferred so `import telemetry` has no side effects -- jr-tests CI (and any
    non-Composio caller) can import this module without composio installed or
    a ~/.composio.key present; only the first real _ex() call needs it."""
    global _client
    if _client is None:
        from composio import Composio
        key = (Path.home() / ".composio.key").read_text().strip()
        _client = Composio(api_key=key)
    return _client


def _ex(slug: str, args: dict):
    r = _composio().tools.execute(slug=slug, user_id=ENTITY, arguments=args, dangerously_skip_version_check=True)
    return r.get("data") if r.get("successful") else None


GA4_BREAKDOWN_DIMS = ["country", "sessionDefaultChannelGroup"]
GA4_BREAKDOWN_METRICS = ["activeUsers", "sessions", "averageSessionDuration", "engagedSessions"]


def _is_junk_segment(channel: str, avg_duration_s: float, engagement_rate: float, *,
                      junk_channel: str = "Direct",
                      max_avg_duration_s: float = 5.0,
                      max_engagement_rate: float = 0.10) -> bool:
    """A behavioral bot/junk rule, matching deep-analytics' bot_filter.py: a segment is junk
    only when its channel is `junk_channel` AND its average session duration is at most
    `max_avg_duration_s` AND its engagement rate is at most `max_engagement_rate`. Country is
    never part of the rule -- humans anywhere can be Direct and fast."""
    return (channel == junk_channel
            and avg_duration_s <= max_avg_duration_s
            and engagement_rate <= max_engagement_rate)


def _ga4_breakdown_totals(rows: list) -> dict:
    """Diagnostic only: segment user memberships can overlap and are not distinct users.

    Sessions are additive here only if the upstream report is complete. The
    published digest obtains distinct user/session totals without dimensions.
    """
    raw = {"segment_user_memberships": 0.0, "sessions": 0.0}
    adjusted = {"segment_user_memberships": 0.0, "sessions": 0.0}
    for row in rows:
        dims = [v.get("value", "") for v in row.get("dimensionValues", [])]
        channel = dims[1] if len(dims) > 1 else ""
        mvals = row.get("metricValues", [])
        m = {name: float(mvals[i]["value"]) if i < len(mvals) else 0.0
             for i, name in enumerate(GA4_BREAKDOWN_METRICS)}
        sessions = m["sessions"]
        engagement_rate = (m["engagedSessions"] / sessions) if sessions else 0.0

        raw["segment_user_memberships"] += m["activeUsers"]
        raw["sessions"] += sessions
        if not _is_junk_segment(channel, m["averageSessionDuration"], engagement_rate):
            adjusted["segment_user_memberships"] += m["activeUsers"]
            adjusted["sessions"] += sessions
    return {"raw": raw, "adjusted": adjusted}


REFERRAL_DENYLIST_PATH = Path(__file__).resolve().parent / "referral_denylist.json"
GA4_SOURCE_METRICS = ["sessions", "engagedSessions", "averageSessionDuration"]
_BARE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_entry(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    host, reason, added_on = entry.get("host"), entry.get("reason"), entry.get("added_on")
    if not (isinstance(host, str) and _BARE_HOST.match(host)):
        return False
    if not (isinstance(reason, str) and reason.strip()):
        return False
    if not (isinstance(added_on, str) and _ISO_DATE.match(added_on)):
        return False
    try:
        dt.date.fromisoformat(added_on)
    except ValueError:
        return False
    return True


def load_referral_denylist(path: Path | None = None) -> frozenset:
    """The committed referral-spam hosts. Fails closed: a missing, unparsable or malformed file
    (any entry without a bare lowercase `host`, a non-blank `reason` and an ISO `added_on`, or a
    duplicate host) raises ValueError -- the digest must never publish unfiltered numbers."""
    path = path or REFERRAL_DENYLIST_PATH
    try:
        entries = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"referral denylist unreadable: {exc}") from exc
    if not isinstance(entries, list):
        raise ValueError("referral denylist must be a JSON list")
    hosts = set()
    for i, entry in enumerate(entries):
        if not _valid_entry(entry):
            raise ValueError(f"referral denylist entry {i} is malformed: {entry!r}")
        if entry["host"] in hosts:
            raise ValueError(f"referral denylist host {entry['host']!r} is duplicated")
        hosts.add(entry["host"])
    return frozenset(hosts)


def _is_denylisted(source: str, denylist: frozenset) -> bool:
    host = source.strip().lower()
    return any(host == d or host.endswith("." + d) for d in denylist)


def _channel_of(source: str) -> str:
    """GA4's Direct channel is exactly the `(direct)` session source; other sources are not
    Direct, which is all _is_junk_segment asks."""
    return "Direct" if source == "(direct)" else source


def spam_adjusted(raw_sessions: float, rows: list, denylist: frozenset) -> dict:
    """Adjusted sessions = raw minus sessionSource rows that are denylisted or behavioural junk
    (each excluded row once); adjusted engaged sessions = all rows' engaged minus the same rows."""
    excluded_sessions = engaged = 0.0
    for row in rows:
        dims = row.get("dimensionValues", [])
        source = dims[0].get("value", "") if dims else ""
        mvals = row.get("metricValues", [])
        m = {name: float(mvals[i]["value"]) if i < len(mvals) else 0.0
             for i, name in enumerate(GA4_SOURCE_METRICS)}
        rate = (m["engagedSessions"] / m["sessions"]) if m["sessions"] else 0.0
        if (_is_denylisted(source, denylist)
                or _is_junk_segment(_channel_of(source), m["averageSessionDuration"], rate)):
            excluded_sessions += m["sessions"]
        else:
            engaged += m["engagedSessions"]
    return {"sessions": int(max(0.0, raw_sessions - excluded_sessions)),
            "engaged_sessions": int(engaged)}


def prior_window(start: str, end: str) -> tuple[str, str]:
    """The equal-length inclusive window ending the day before `start`."""
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    prior_end = s - dt.timedelta(days=1)
    return (prior_end - (e - s)).isoformat(), prior_end.isoformat()


def delta_line(label: str, current, prior) -> str:
    if current is None or prior is None:
        return f"📈 28d {label}: unavailable"
    arrow = "↑" if current > prior else "↓" if current < prior else "→"
    return f"📈 28d {label}: {arrow} {current} vs {prior} prior 28d"


def top_search_demand(rows: list, n: int = 6, min_impressions: int = MIN_IMPRESSIONS) -> list:
    """The weekly digest's "Top search demand" rows: GSC query rows at or above the demand miner's
    own impression floor (MIN_IMPRESSIONS), first `n` — no 1-impression noise."""
    return [r for r in rows if (r.get("impressions") or 0) >= min_impressions][:n]


def completed_window(days: int = 7, today_utc: dt.date | None = None) -> tuple[str, str]:
    """Inclusive dates with a two-day UTC lag, complete in every property timezone."""
    if days < 1:
        raise ValueError("days must be positive")
    today = today_utc or dt.datetime.now(dt.timezone.utc).date()
    end = today - dt.timedelta(days=2)
    start = end - dt.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _ga4_source_rows(start: str, end: str) -> list | None:
    """The sessionSource breakdown behind the spam-adjusted numbers; None when the fetch fails."""
    ga = _ex("GOOGLE_ANALYTICS_RUN_REPORT", {"property": GA4_PROPERTY,
             "dateRanges": [{"startDate": start, "endDate": end}],
             "dimensions": [{"name": "sessionSource"}],
             "metrics": [{"name": name} for name in GA4_SOURCE_METRICS]})
    return None if ga is None else ga.get("rows", [])


def _adjusted_engaged(start: str, end: str, denylist: frozenset) -> int | None:
    rows = _ga4_source_rows(start, end)
    return None if rows is None else spam_adjusted(0, rows, denylist)["engaged_sessions"]


def _gsc_total(start: str, end: str) -> dict | None:
    tot = _ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
              {"siteUrl": GSC_SITE, "startDate": start, "endDate": end, "dimensions": [], "rowLimit": 1})
    return ((tot or {}).get("rows") or [None])[0]


def _gsc_clicks(start: str, end: str) -> int | None:
    t = _gsc_total(start, end)
    return None if t is None else t.get("clicks", 0)


def _ga4_line(start: str, end: str, denylist: frozenset) -> str:
    ga = _ex("GOOGLE_ANALYTICS_RUN_REPORT", {"property": GA4_PROPERTY,
             "dateRanges": [{"startDate": start, "endDate": end}],
             "dimensions": [],
             "metrics": [{"name": "activeUsers"}, {"name": "sessions"}]})
    try:
        row = ga["rows"][0]["metricValues"]
        users, sessions = int(float(row[0]["value"])), int(float(row[1]["value"]))
    except Exception:
        return "👥 GA4: unavailable (no complete no-dimension total)"
    raw = f"👥 GA4: raw *{users}* distinct active users / {sessions} sessions"
    rows = _ga4_source_rows(start, end)
    if rows is None:
        return raw + " · spam-adjusted unavailable"
    adj = spam_adjusted(sessions, rows, denylist)
    return raw + f" · spam-adjusted {adj['sessions']} sessions / {adj['engaged_sessions']} engaged sessions"


def _growth_lines(denylist: frozenset) -> list:
    """GSC clicks and adjusted engaged sessions: the completed 28d window vs the 28d before it."""
    cur = completed_window(28)
    prev = prior_window(*cur)
    return [delta_line("GSC clicks", _gsc_clicks(*cur), _gsc_clicks(*prev)),
            delta_line("adjusted engaged sessions",
                       _adjusted_engaged(*cur, denylist), _adjusted_engaged(*prev, denylist))]


def weekly_digest(days: int = 7) -> str:
    denylist = load_referral_denylist(REFERRAL_DENYLIST_PATH)   # fail closed before any fetch
    S, E = completed_window(days)

    ga_line = _ga4_line(S, E, denylist)

    t = _gsc_total(S, E)
    if t is None:
        gsc_line = "🔎 GSC: unavailable (fetch failed or returned no total row)"
    else:
        clicks, imps = t.get("clicks", 0), t.get("impressions", 0)
        ctr = round(clicks / imps * 100, 2) if imps else 0.0
        pos = round(t.get("position", 0), 1)
        gsc_line = f"🔎 GSC: {clicks} clicks · {imps} impressions · {ctr}% CTR · avg pos {pos}"

    tq = _ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
             {"siteUrl": GSC_SITE, "startDate": S, "endDate": E, "dimensions": ["query"], "rowLimit": 50})
    queries = top_search_demand((tq or {}).get("rows", []))

    lines = [f"🤖 *Jr — weekly telemetry* · esp-atlas.com · {S}→{E}",
             ga_line,
             gsc_line,
             *_growth_lines(denylist),
             GOAL_LINE,
             "",
             "*Top search demand* — Jr's data-priority signal:"]
    if not queries:
        lines.append("  (no query above the miner's impression floor this week)")
    for r in queries:
        lines.append(f"  • `{r['keys'][0]}` — imp {r.get('impressions')}, pos {round(r.get('position', 0), 1)}")
    msg = "\n".join(lines)

    snap = Path(__file__).resolve().parent.parent / "docs" / "telemetry" / f"{E}.md"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text("# esp-atlas telemetry — " + E + "\n\n" + msg + "\n")
    notify.send_telegram(msg)
    return msg


if __name__ == "__main__":
    print(weekly_digest())
