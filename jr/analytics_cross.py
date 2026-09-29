"""EspAtlas Jr — analytics crossing: GA4 x Search Console joined on landing page
(SPEC-analytics-cross.md).

Exposes the acquisition -> activation funnel today's telemetry cannot see: which query
lands on which page, and what that page's visitors do next (page_view -> part_view ->
flash_open). Reuses jr/telemetry.py's Composio calling convention EXACTLY -- same _ex(),
same GA4_PROPERTY/GSC_SITE, no new auth path. The Google Trends demand axis (SPEC §7) is
the one exception: it's unofficial and outside Composio, fetched via the `pytrends` pip
dep through its own fetch_trends() wrapper.

build_funnel() is the pure, network-free core: it takes already-fetched raw API rows and
never raises, degrading gracefully when a source axis is missing (SPEC §6). The fetch_*
functions are thin one-call wrappers around telemetry._ex() (or, for fetch_trends(),
pytrends) and are not oracle-tested (mocked instead) -- all join/scoring logic lives in
build_funnel(), which is.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telemetry  # noqa: E402 -- reuses _ex(), GA4_PROPERTY, GSC_SITE

try:
    from pytrends.request import TrendReq  # noqa: E402 -- unofficial Trends client (SPEC §7)
except ImportError:
    TrendReq = None

TRENDS_KW_LIST_CAP = 5  # pytrends hard-caps kw_list at 5 terms per payload
TRENDS_TIMEFRAME = "today 1-m"

FUNNEL_EVENT_NAMES = ("part_view", "flash_open")
STRIKING_DISTANCE_MIN = 8
STRIKING_DISTANCE_MAX = 20
LEAK_MIN_IMPRESSIONS = 10
LEAK_MAX_POSITION = 20
LEAK_MAX_CONVERSION = 0.05
TOP_QUERIES_CAP = 10
AXES = ("ga_pages", "ga_events", "gsc_pages", "gsc_queries")


def normalize_page(url_or_path: str) -> str:
    """Join key: strips scheme/host/query/fragment, decodes percent-encoding, strips a
    single trailing slash (except for the root "/"). Case is preserved (SPEC §3)."""
    path = unquote(urlsplit(url_or_path).path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path


# --- fetch layer (thin, network, untested-by-oracle on purpose -- SPEC §1/§6) --------------


def fetch_ga_pages(start: str, end: str):
    data = telemetry._ex("GOOGLE_ANALYTICS_RUN_REPORT", {
        "property": telemetry.GA4_PROPERTY,
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}, {"name": "sessions"}],
    })
    return None if data is None else data.get("rows", [])


def fetch_ga_events(start: str, end: str):
    data = telemetry._ex("GOOGLE_ANALYTICS_RUN_REPORT", {
        "property": telemetry.GA4_PROPERTY,
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "pagePath"}, {"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
    })
    return None if data is None else data.get("rows", [])


def fetch_gsc_pages(start: str, end: str):
    data = telemetry._ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY", {
        "siteUrl": telemetry.GSC_SITE, "startDate": start, "endDate": end,
        "dimensions": ["page"], "rowLimit": 1000,
    })
    return None if data is None else data.get("rows", [])


def fetch_gsc_queries(start: str, end: str):
    data = telemetry._ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY", {
        "siteUrl": telemetry.GSC_SITE, "startDate": start, "endDate": end,
        "dimensions": ["query", "page"], "rowLimit": 1000,
    })
    return None if data is None else data.get("rows", [])


def fetch_trends(queries: list) -> dict:
    """Latest non-partial Google Trends relative-interest score (0-100) per query, over the
    trailing month. Trends is an unofficial, blockable source outside telemetry.py's Composio
    convention (SPEC §7) -- ANY failure (import, network, empty frame) degrades to {} so a
    Trends outage never breaks the tick, matching the other fetch_* functions."""
    if not queries or TrendReq is None:
        return {}
    try:
        terms = queries[:TRENDS_KW_LIST_CAP]
        client = TrendReq(hl="en-US", tz=0)
        client.build_payload(terms, timeframe=TRENDS_TIMEFRAME)
        df = client.interest_over_time()
        if df is None or df.empty:
            return {}
        if "isPartial" in df.columns:
            df = df[~df["isPartial"].astype(bool)]
        if df.empty:
            return {}
        latest = df.iloc[-1]
        return {term: int(latest[term]) for term in terms if term in latest}
    except Exception:
        return {}


# --- parsing: raw API rows -> {normalized_page: stats} -------------------------------------


def _parse_ga_pages(rows: list) -> dict:
    out = {}
    for row in rows:
        page = normalize_page(row["dimensionValues"][0]["value"])
        views, users, sessions = (int(mv["value"]) for mv in row["metricValues"])
        out[page] = {"page_views": views, "active_users": users, "sessions": sessions}
    return out


def _parse_ga_events(rows: list) -> dict:
    out = {}
    for row in rows:
        page = normalize_page(row["dimensionValues"][0]["value"])
        event = row["dimensionValues"][1]["value"]
        if event not in FUNNEL_EVENT_NAMES:
            continue
        count = int(row["metricValues"][0]["value"])
        bucket = out.setdefault(page, {})
        bucket[event] = bucket.get(event, 0) + count
    return out


def _parse_gsc_pages(rows: list) -> dict:
    buckets = {}
    for row in rows:
        page = normalize_page(row["keys"][0])
        buckets.setdefault(page, []).append(row)
    out = {}
    for page, page_rows in buckets.items():
        impressions = sum(int(r.get("impressions", 0)) for r in page_rows)
        clicks = sum(int(r.get("clicks", 0)) for r in page_rows)
        ctr = (clicks / impressions) if impressions else 0.0
        weighted = [(r["position"], int(r.get("impressions", 0))) for r in page_rows if r.get("position") is not None]
        pos_impressions = sum(i for _, i in weighted)
        avg_position = (sum(p * i for p, i in weighted) / pos_impressions) if pos_impressions else None
        out[page] = {"impressions": impressions, "clicks": clicks, "ctr": ctr, "avg_position": avg_position}
    return out


def _parse_gsc_queries(rows: list) -> dict:
    out = {}
    for row in rows:
        query, raw_page = row["keys"]
        page = normalize_page(raw_page)
        out.setdefault(page, []).append({
            "query": query,
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "position": row.get("position"),
        })
    return out


# --- pure transform: the funnel join (SPEC §2/§4/§5/§6) -------------------------------------


def _rate(numerator, denominator):
    """None when either side is unavailable or denominator is 0 -- never a fabricated rate."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _build_row(page: str, ga_page_stats, ga_event_stats, gsc_page_stats, gsc_query_stats, trends: dict) -> dict:
    if ga_page_stats is None:
        page_views = active_users = sessions = None
    else:
        pv = ga_page_stats.get(page)
        page_views = pv["page_views"] if pv else 0
        active_users = pv["active_users"] if pv else 0
        sessions = pv["sessions"] if pv else 0

    if ga_event_stats is None:
        part_view = flash_open = None
    else:
        ev = ga_event_stats.get(page, {})
        part_view = ev.get("part_view", 0)
        flash_open = ev.get("flash_open", 0)

    if gsc_page_stats is None:
        impressions = clicks = ctr = avg_position = None
    else:
        gp = gsc_page_stats.get(page)
        if gp is None:
            impressions = clicks = 0
            ctr = avg_position = None  # undefined at zero rows, not a fabricated 0.0
        else:
            impressions, clicks, ctr, avg_position = gp["impressions"], gp["clicks"], gp["ctr"], gp["avg_position"]

    queries = [] if gsc_query_stats is None else gsc_query_stats.get(page, [])
    top_queries = sorted(queries, key=lambda q: q["impressions"], reverse=True)[:TOP_QUERIES_CAP]
    demand = trends.get(top_queries[0]["query"]) if top_queries else None

    conv_view_to_part = _rate(part_view, page_views)
    conv_part_to_flash = _rate(flash_open, part_view)

    striking_distance = any(
        q["position"] is not None
        and STRIKING_DISTANCE_MIN <= q["position"] <= STRIKING_DISTANCE_MAX
        and q["impressions"] > 0
        for q in queries
    )
    leak_flag = (
        impressions is not None and impressions >= LEAK_MIN_IMPRESSIONS
        and avg_position is not None and avg_position <= LEAK_MAX_POSITION
        and conv_view_to_part is not None and conv_view_to_part < LEAK_MAX_CONVERSION
    )

    return {
        "page": page,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "avg_position": avg_position,
        "page_views": page_views,
        "active_users": active_users,
        "sessions": sessions,
        "part_view": part_view,
        "flash_open": flash_open,
        "conv_view_to_part": conv_view_to_part,
        "conv_part_to_flash": conv_part_to_flash,
        "top_queries": top_queries,
        "demand": demand,  # Google Trends relative-interest score (0-100) for the top query (SPEC §7)
        "striking_distance": striking_distance,
        "leak_flag": leak_flag,
    }


def build_funnel(ga_pages, ga_events, gsc_pages, gsc_queries, trends: dict = None) -> dict:
    """Pure, network-free join of the four already-fetched source axes into a FunnelTable.

    Each axis is `None` (source call failed -- marked unavailable, fields go None) or a
    `list[dict]` of raw rows in the shape the matching fetch_* function returns (possibly
    empty -- a real "loaded, zero rows" result, distinct from unavailable). Never raises.

    `trends` is an already-fetched `{query: 0..100}` map (fetch_trends' return shape, SPEC
    §7); a row's `demand` is the score for its top query when present, else None. Absent or
    empty, every row's demand stays None -- the same graceful degradation as the other axes.
    """
    raw = {"ga_pages": ga_pages, "ga_events": ga_events, "gsc_pages": gsc_pages, "gsc_queries": gsc_queries}
    unavailable = [name for name in AXES if raw[name] is None]
    trends = trends or {}

    ga_page_stats = None if ga_pages is None else _parse_ga_pages(ga_pages)
    ga_event_stats = None if ga_events is None else _parse_ga_events(ga_events)
    gsc_page_stats = None if gsc_pages is None else _parse_gsc_pages(gsc_pages)
    gsc_query_stats = None if gsc_queries is None else _parse_gsc_queries(gsc_queries)

    pages = set(ga_page_stats or {}) | set(gsc_page_stats or {})
    rows = [_build_row(page, ga_page_stats, ga_event_stats, gsc_page_stats, gsc_query_stats, trends) for page in pages]
    rows.sort(key=lambda r: (
        -(r["impressions"] if r["impressions"] is not None else -1),
        -(r["page_views"] if r["page_views"] is not None else -1),
    ))

    return {
        "rows": rows,
        "unavailable": unavailable,
        "generated_from": {name: len(raw[name]) if raw[name] is not None else 0 for name in AXES},
    }


def _top_query_per_page(gsc_queries) -> list:
    """The query each page would surface as top_queries[0] in build_funnel -- the set fed to
    fetch_trends, so the Trends call only ever asks about queries that can actually join."""
    if not gsc_queries:
        return []
    query_stats = _parse_gsc_queries(gsc_queries)
    top = []
    for page_queries in query_stats.values():
        ranked = sorted(page_queries, key=lambda q: q["impressions"], reverse=True)
        if ranked:
            top.append(ranked[0]["query"])
    return top


def weekly_funnel(days: int = 7) -> dict:
    """Convenience orchestrator: fetches all four axes over the trailing `days`, fetches
    Google Trends for each page's top query, and joins them. No Telegram/snapshot wiring here
    (SPEC §8 non-goals) -- callers decide what to do with the returned FunnelTable."""
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    start_s, end_s = start.isoformat(), end.isoformat()
    gsc_queries = fetch_gsc_queries(start_s, end_s)
    trends = fetch_trends(_top_query_per_page(gsc_queries))
    return build_funnel(
        fetch_ga_pages(start_s, end_s),
        fetch_ga_events(start_s, end_s),
        fetch_gsc_pages(start_s, end_s),
        gsc_queries,
        trends,
    )


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(weekly_funnel(), indent=2))
