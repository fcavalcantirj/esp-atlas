"""EspAtlas Jr — the weekly Feature usage report (jr/feature_usage.py), owner's question 2026-11-18:
"do we track deeply how people use the website, to focus — e.g. the atlas, do people use it?"

For every feature in `jr/features.json` it counts, over the completed 28-day window and the three before it
(four GA4 date ranges in one request):
  - reached: distinct users who viewed one of its pages (None for features that live on many pages and
    would only restate site traffic, i.e. prefix-only features);
  - used: distinct users who fired one of its action events (user-initiated events only), on one of its
    pages when it has pages — the same action fired elsewhere (the home page runs the wizard query too) is
    not this feature's use, and "used" stays a part of the "reached" it is divided by;
  - use rate = used / reached, events per user who used it.
Maintainers are left out with `customEvent:internal != "1"` (apps/web `?internal=1`); while that dimension
is not registered in GA4 a filtered probe fails where the unfiltered one answers, so the whole report runs
without it and says so on its own line — never silently. The probe decides once: one failed call later is
that feature's row ("unavailable"), never a switch of basis. Crawlers rarely fire custom action events, so "used" is the bot-resistant number; "reached"
counts every page view and is printed as such.

A feature with fewer than `low_use_acting_users` users who used it in each of the last `low_use_windows`
windows is flagged "low use" — a report for the owner to decide on, never an automated removal.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

FEATURES_PATH = Path(__file__).resolve().parent / "features.json"
WINDOWS = 4                     # GA4 runReport accepts at most four date ranges per request
WINDOW_DAYS = 28


def load_features(path: Path = FEATURES_PATH) -> dict:
    """The committed feature map; fails closed on a malformed file (a wrong map must not print numbers)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = doc.get("features")
    if not isinstance(feats, dict) or not feats:
        raise ValueError("features.json has no features")
    for name, f in feats.items():
        if not isinstance(f, dict) or not isinstance(f.get("events"), list) or not f["events"]:
            raise ValueError(f"feature {name!r} has no action events")
        for key in ("pages", "page_prefixes"):
            if not isinstance(f.get(key, []), list):
                raise ValueError(f"feature {name!r}: {key} must be a list")
    return doc


def windows(end: str, n: int = WINDOWS, days: int = WINDOW_DAYS) -> list[tuple[str, str]]:
    """`n` back-to-back inclusive windows ending at `end`, newest first."""
    e = dt.date.fromisoformat(end)
    out = []
    for _ in range(n):
        s = e - dt.timedelta(days=days - 1)
        out.append((s.isoformat(), e.isoformat()))
        e = s - dt.timedelta(days=1)
    return out


def _in_list(field_name: str, values: list) -> dict:
    return {"filter": {"fieldName": field_name, "inListFilter": {"values": list(values)}}}


def _page_filter(pages: list, prefixes: list) -> dict | None:
    exprs = ([_in_list("pagePath", pages)] if pages else []) + [
        {"filter": {"fieldName": "pagePath", "stringFilter": {"matchType": "BEGINS_WITH", "value": p}}} for p in prefixes]
    if not exprs:
        return None
    return exprs[0] if len(exprs) == 1 else {"orGroup": {"expressions": exprs}}


NOT_INTERNAL = {"notExpression": {"filter": {"fieldName": "customEvent:internal",
                                             "stringFilter": {"matchType": "EXACT", "value": "1"}}}}


def _with_internal(expr: dict, exclude_internal: bool) -> dict:
    return {"andGroup": {"expressions": [expr, NOT_INTERNAL]}} if exclude_internal else expr


def _request(property_id: str, wins: list, expr: dict | None, metrics: list) -> dict:
    req = {"property": property_id,
           "dateRanges": [{"startDate": s, "endDate": e, "name": f"w{i}"} for i, (s, e) in enumerate(wins)],
           "dimensions": [], "metrics": [{"name": m} for m in metrics]}
    if expr is not None:
        req["dimensionFilter"] = expr
    return req


def _internal_filter_works(ex, property_id: str, wins: list) -> bool:
    """Decided once per report, measured: False only when a probe filtered on `internal` fails AND the same
    probe without the filter succeeds (the dimension is not registered). A GA4 that answers neither keeps
    the filter on: no cause is named that was not observed, and every row still shares one basis."""
    if ex("GOOGLE_ANALYTICS_RUN_REPORT", _request(property_id, wins, NOT_INTERNAL, ["totalUsers"])) is not None:
        return True
    return ex("GOOGLE_ANALYTICS_RUN_REPORT", _request(property_id, wins, None, ["totalUsers"])) is None


def _by_window(resp: dict | None, n: int) -> list[list[float]] | None:
    """Metric values per window w0..w{n-1} (missing window = zeros); None when the call failed."""
    if resp is None:
        return None
    out = [[0.0, 0.0] for _ in range(n)]
    for row in resp.get("rows", []) or []:
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        name = next((d for d in dims if d.startswith("w") and d[1:].isdigit()), "w0")
        i = int(name[1:])
        if i < n:
            out[i] = [float(m.get("value", 0) or 0) for m in row.get("metricValues", [])] + [0.0] * 2
    return out


@dataclass
class FeatureRow:
    name: str
    reached: list | None            # users per window (None: not a page feature)
    used: list                      # users per window
    events: list                    # action events per window
    low_use: bool = False


@dataclass
class Report:
    end: str
    rows: list = field(default_factory=list)
    internal_excluded: bool = True
    unavailable: list = field(default_factory=list)


def build(ex, property_id: str, end: str, features_doc: dict | None = None) -> Report:
    """The report for the four windows ending at `end`. `ex(slug, args)` is telemetry._ex (None on failure)."""
    doc = features_doc or load_features()
    wins = windows(end)
    rep = Report(end=end, internal_excluded=_internal_filter_works(ex, property_id, wins))

    def run(expr: dict, metrics: list):           # a failed call is that feature's row only, never a new basis
        req = _request(property_id, wins, _with_internal(expr, rep.internal_excluded), metrics)
        return _by_window(ex("GOOGLE_ANALYTICS_RUN_REPORT", req), len(wins))

    threshold = int(doc.get("low_use_acting_users", 5))
    n_low = int(doc.get("low_use_windows", WINDOWS))
    for name, f in doc["features"].items():
        page = _page_filter(f["pages"], []) if f.get("pages") else None   # prefix-only: would restate traffic
        acts = _in_list("eventName", f["events"])
        # a page feature's action counts on its own pages only: '/' also fires wizard_submit, /wizard example_click
        used = run(acts if page is None else {"andGroup": {"expressions": [page, acts]}}, ["totalUsers", "eventCount"])
        if used is None:
            rep.unavailable.append(name)
            continue
        reached = None
        if page is not None:
            got = run({"andGroup": {"expressions": [page, _in_list("eventName", ["page_view"])]}}, ["totalUsers", "eventCount"])
            reached = None if got is None else [int(w[0]) for w in got]
        users = [int(w[0]) for w in used]
        events = [int(w[1]) for w in used]
        rep.rows.append(FeatureRow(name, reached, users, events,
                                   low_use=all(u < threshold for u in users[:n_low])))
    rep.rows.sort(key=lambda r: (-r.used[0], r.name))
    return rep


def _arrow(cur: int, prev: int) -> str:
    return "↑" if cur > prev else "↓" if cur < prev else "→"


def _md(text: str) -> str:
    """Escape what Telegram's legacy Markdown (notify.send_telegram, parse_mode "Markdown") would read as
    markup in a plain name: an underscore opens italics, so part_pages / firmware_index / home_ask would break
    the whole message (review BLOCK on #1842)."""
    return "".join("\\" + c if c in "_*`[" else c for c in text)


def lines(rep: Report) -> list[str]:
    """The digest section: one line per feature, newest window first, vs the window before."""
    out = ["*Feature usage* — users who used each feature, last 28d (vs prior 28d)"
           + (" · maintainers excluded" if rep.internal_excluded else
              " · ⚠ maintainers NOT excluded (GA4 dimension `internal` not registered yet)") + ":"]
    for r in rep.rows:
        u0, u1 = r.used[0], r.used[1] if len(r.used) > 1 else 0
        reach = ""
        if r.reached is not None:
            rate = f" ({round(100 * u0 / r.reached[0])} %)" if r.reached[0] else ""
            reach = f" of {r.reached[0]} who reached it{rate}"
        per = f" · {round(r.events[0] / u0, 1)} actions each" if u0 else ""
        flag = " · low use 4 windows" if r.low_use else ""
        out.append(f"  • {_md(r.name)} — {u0}{reach}{per} · {_arrow(u0, u1)} vs {u1}{flag}")
    for name in rep.unavailable:
        out.append(f"  • {_md(name)} — unavailable (GA4 call failed)")
    return out


def main(argv=None) -> int:
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry
    ap = argparse.ArgumentParser(description="Print the Feature usage report for the latest completed window.")
    ap.add_argument("--end", help="window end date (default: the completed 28-day window's end)")
    a = ap.parse_args(argv)
    end = a.end or telemetry.completed_window(WINDOW_DAYS)[1]
    print("\n".join(lines(build(telemetry._ex, telemetry.GA4_PROPERTY, end))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
