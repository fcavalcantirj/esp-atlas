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
from composio import Composio

KEY = (Path.home() / ".composio.key").read_text().strip()
ENTITY = "7UQIn73xcXnpKIQiaTJzjrCRZk0VznPv"
GA4_PROPERTY = "properties/551132215"
GSC_SITE = "sc-domain:esp-atlas.com"
TARGET_DATE = dt.date(2026, 11, 27)   # 1MM-user north-star (§3d)
_c = Composio(api_key=KEY)


def _ex(slug: str, args: dict):
    r = _c.tools.execute(slug=slug, user_id=ENTITY, arguments=args, dangerously_skip_version_check=True)
    return r.get("data") if r.get("successful") else None


def weekly_digest(days: int = 7) -> str:
    end = dt.date.today(); start = end - dt.timedelta(days=days)
    S, E = start.isoformat(), end.isoformat()

    ga = _ex("GOOGLE_ANALYTICS_RUN_REPORT", {"property": GA4_PROPERTY,
             "dateRanges": [{"startDate": S, "endDate": E}],
             "metrics": [{"name": "activeUsers"}, {"name": "newUsers"}, {"name": "sessions"}]})
    try:
        users, new, sess = (m["value"] for m in ga["rows"][0]["metricValues"])
    except Exception:
        users = new = sess = "?"

    tot = _ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
              {"siteUrl": GSC_SITE, "startDate": S, "endDate": E, "dimensions": [], "rowLimit": 1})
    t = ((tot or {}).get("rows") or [{}])[0]
    clicks, imps = t.get("clicks", 0), t.get("impressions", 0)
    ctr, pos = round(t.get("ctr", 0) * 100, 2), round(t.get("position", 0), 1)

    tq = _ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
             {"siteUrl": GSC_SITE, "startDate": S, "endDate": E, "dimensions": ["query"], "rowLimit": 6})
    queries = (tq or {}).get("rows", [])

    days_left = (TARGET_DATE - end).days
    lines = [f"🤖 *Jr — weekly telemetry* · esp-atlas.com · {S}→{E}",
             f"👥 GA4: *{users}* users ({new} new) · {sess} sessions",
             f"🔎 GSC: {clicks} clicks · {imps} impressions · {ctr}% CTR · avg pos {pos}",
             f"🎯 1,000,000 by {TARGET_DATE} — **{days_left} days left**",
             "",
             "*Top search demand* — Jr's data-priority signal:"]
    for r in queries[:6]:
        lines.append(f"  • `{r['keys'][0]}` — imp {r.get('impressions')}, pos {round(r.get('position', 0), 1)}")
    msg = "\n".join(lines)

    snap = Path(__file__).resolve().parent.parent / "docs" / "telemetry" / f"{E}.md"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text("# esp-atlas telemetry — " + E + "\n\n" + msg + "\n")
    notify.send_telegram(msg)
    return msg


if __name__ == "__main__":
    print(weekly_digest())
