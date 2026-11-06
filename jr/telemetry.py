"""EspAtlas Jr — weekly growth telemetry (§3d).

Pulls GA4 + Search Console for esp-atlas.com via **Composio OAuth** (no service-account key),
sends a weekly digest to Telegram, and writes a git-tracked snapshot. GSC top-demand queries
are surfaced as Jr's data-priority signal. Run with the composio venv:

    ~/.composio-venv/bin/python telemetry.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify  # stdlib-only

ENTITY = "7UQIn73xcXnpKIQiaTJzjrCRZk0VznPv"
GA4_PROPERTY = "properties/551132215"
GSC_SITE = "sc-domain:esp-atlas.com"
TARGET_DATE = dt.date(2026, 11, 27)   # 1MM-user north-star (§3d)
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


def weekly_digest(days: int = 7) -> str:
    S, E = completed_window(days)
    end = dt.date.fromisoformat(E)

    ga = _ex("GOOGLE_ANALYTICS_RUN_REPORT", {"property": GA4_PROPERTY,
             "dateRanges": [{"startDate": S, "endDate": E}],
             "dimensions": [],
             "metrics": [{"name": "activeUsers"}, {"name": "sessions"}]})
    try:
        row = ga["rows"][0]["metricValues"]
        ga_line = f"👥 GA4: *{int(float(row[0]['value']))}* distinct active users / {int(float(row[1]['value']))} sessions"
    except Exception:
        ga_line = "👥 GA4: unavailable (no complete no-dimension total)"

    tot = _ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
              {"siteUrl": GSC_SITE, "startDate": S, "endDate": E, "dimensions": [], "rowLimit": 1})
    t = ((tot or {}).get("rows") or [None])[0]
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

    days_left = (TARGET_DATE - dt.datetime.now(dt.timezone.utc).date()).days
    lines = [f"🤖 *Jr — weekly telemetry* · esp-atlas.com · {S}→{E}",
             ga_line,
             gsc_line,
             f"🎯 1,000,000 by {TARGET_DATE} — **{days_left} days left**",
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
