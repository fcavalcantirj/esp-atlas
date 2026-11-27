"""EspAtlas Jr — outcome attribution (jr/outcomes.py; SPEC-outcome-attribution.md, united plan step B).

What did Jr's shipped changes do to site activity? Changes come from main's first-parent history (no new state);
activity comes from Search Console page totals by page and date (final data, Pacific dates). Each cohort (lane,
kind, Pacific ISO week) is measured as a difference in differences against untouched pages of the same type, for
7/14/28-day windows; +28 is the verdict, a window not fully in the past is `immature`. Measurement only: nothing
here changes what Jr does.

    python3 jr/outcomes.py --since 2026-09-01          # prints the cohort table; JSON to JR_STATE_DIR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
PACIFIC = ZoneInfo("America/Los_Angeles")
INDEXING_LAG_DAYS = 3          # post window starts this many days after the change day
FINAL_LAG_DAYS = 3             # GSC data is final a few days after the date
WINDOWS = (7, 14, 28)
MIN_CONTROL_PRE = 100          # control impressions in the pre window below this: the site trend is noise, no effect
_FIRMWARE = re.compile(r"^data/firmware/([^/]+)/firmware\.md$")
_BOARD = re.compile(r"^data/boards/[^/]+/([^/]+)/board\.md$")
_RECIPE = re.compile(r"^data/recipes/([^/]+)__([^/]+)/recipe\.md$")


def lane_of(subject: str) -> str:
    """The lane a merge belongs to, from its merge subject (a merge commit names the branch; a squash names the
    PR title Jr wrote)."""
    s = subject or ""
    if re.search(r"jr/tick-\S*-bf\b", s) or s.startswith("feat(jr): backfill"):
        return "backfill"
    if "jr/tick-" in s or s.startswith(("feat(jr): tick", "chore(jr): tick")):
        return "tick"
    if "jr/research-" in s or "jr/demand-" in s or s.startswith("chore(jr): demand"):
        return "demand"
    return "person"


def _urls(path: str) -> list[str]:
    if (m := _FIRMWARE.match(path)):
        return [f"/firmware/{m.group(1)}"]
    if (m := _BOARD.match(path)):
        return [f"/parts/{m.group(1)}"]
    if (m := _RECIPE.match(path)):
        return [f"/parts/{m.group(1)}", f"/firmware/{m.group(2)}"]
    return []


def changes_from_log(text: str) -> list[dict]:
    """Parse `git log --first-parent --format='@@ %h %cI %s' --name-status -- data/` output into changes:
    {sha, at (UTC iso), day (Pacific date), urls, kind (added|modified), lane}. Merges with no record are dropped."""
    out, cur = [], None
    for line in (text or "").splitlines():
        if line.startswith("@@ "):
            parts = line[3:].split(" ", 2)
            at = datetime.fromisoformat(parts[1].replace("Z", "+00:00"))
            cur = {"sha": parts[0], "at": at.astimezone(timezone.utc).isoformat(), "day": at.astimezone(PACIFIC).date(),
                   "urls": [], "kind": "modified", "lane": lane_of(parts[2] if len(parts) > 2 else "")}
            out.append(cur)
            continue
        if cur is None or "\t" not in line:
            continue
        status, path = line.split("\t")[0], line.split("\t")[-1]
        urls = _urls(path)
        if not urls or status[:1] not in ("A", "M"):
            continue
        if status.startswith("A"):
            cur["kind"] = "added"
        for u in urls:
            if u not in cur["urls"]:
                cur["urls"].append(u)
    return [c for c in out if c["urls"]]


def page_days(rows: list) -> dict:
    """{(path, date): (clicks, impressions)} from GSC rows with keys [page url, YYYY-MM-DD]."""
    out = {}
    for r in rows or []:
        keys = r.get("keys") or []
        if len(keys) < 2:
            continue
        path = unquote(urlsplit(keys[0]).path)
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        d = date.fromisoformat(keys[1])
        c, i = out.get((path, d), (0, 0))
        out[(path, d)] = (c + int(r.get("clicks") or 0), i + int(r.get("impressions") or 0))
    return out


def _sum(pd: dict, pages, start: date, days: int, idx: int = 1) -> int:
    return sum(pd.get((p, start + timedelta(k)), (0, 0))[idx] for p in pages for k in range(days))


def cohort_effects(changes: list, pd: dict, today: date, windows=WINDOWS) -> list[dict]:
    """One entry per cohort (lane, kind, Pacific ISO week): treated pages, and per window the treated pre/post
    impressions, the control ratio, the difference-in-differences effect and whether the window is mature."""
    cohorts = defaultdict(list)
    for c in changes:
        y, w, _ = c["day"].isocalendar()
        cohorts[(c["lane"], c["kind"], f"{y}-W{w:02d}")].append(c)
    all_pages = {p for (p, _d) in pd}
    out = []
    for (lane, kind, week), cs in sorted(cohorts.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        day = min(c["day"] for c in cs)
        treated = sorted({u for c in cs for u in c["urls"]})
        entry = {"lane": lane, "kind": kind, "week": week, "day": day.isoformat(), "pages": len(treated),
                 "shas": [c["sha"] for c in cs], "windows": {}}
        for W in windows:
            post_start = day + timedelta(INDEXING_LAG_DAYS)
            mature = today >= post_start + timedelta(W + FINAL_LAG_DAYS)
            busy = {u for c in changes if day - timedelta(W) <= c["day"] <= post_start + timedelta(W) for u in c["urls"]}
            types = {"/" + t.split("/")[1] + "/" for t in treated}
            control = sorted(p for p in all_pages if p not in busy and any(p.startswith(t) for t in types))
            post = _sum(pd, treated, post_start, W) if mature else None
            cpre, cpost = _sum(pd, control, day - timedelta(W), W), _sum(pd, control, post_start, W)
            ratio = (cpost / cpre) if cpre >= MIN_CONTROL_PRE else None
            if kind == "added":
                entry["windows"][W] = {"pre": None, "post": post, "control_ratio": ratio, "effect": None,
                                       "mature": mature, "control_pages": len(control)}
                continue
            pre = _sum(pd, treated, day - timedelta(W), W)
            effect = (post - pre) - pre * (ratio - 1) if (mature and ratio is not None) else None
            entry["windows"][W] = {"pre": pre, "post": post, "control_ratio": ratio, "effect": effect,
                                   "mature": mature, "control_pages": len(control)}
        out.append(entry)
    return out


# --- live run (the runner's daily telemetry job) -----------------------------------------------------------------

def git_log(since: str, repo: Path = REPO) -> str:
    return subprocess.run(["git", "log", "--first-parent", "origin/main", f"--since={since}",
                           "--format=@@ %h %cI %s", "--name-status", "--", "data/"],
                          cwd=repo, capture_output=True, text=True, check=True).stdout


def fetch_page_days(start: str, end: str, ex=None) -> list:
    """GSC page x date totals, paginated (25,000 rows a call), final data only."""
    if ex is None:
        import telemetry
        ex = telemetry._ex
        site = telemetry.GSC_SITE
    else:
        site = "sc-domain:esp-atlas.com"
    rows, start_row = [], 0
    while True:
        data = ex("GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY", {
            "siteUrl": site, "startDate": start, "endDate": end, "dimensions": ["page", "date"],
            "rowLimit": 25000, "startRow": start_row, "dataState": "final"}) or {}
        batch = data.get("rows") or []
        rows += batch
        if len(batch) < 25000:
            return rows
        start_row += len(batch)


def report_lines(cohorts: list, window: int = 28) -> list[str]:
    lines = [f"*Outcomes* (impressions, +{window} d verdict; DiD vs untouched pages of the same type)"]
    for c in cohorts:
        w = c["windows"].get(window) or {}
        if not w.get("mature"):
            continue
        eff = ("n/a (new pages)" if c["kind"] == "added" else "n/a (control too thin)") if w["effect"] is None \
            else f"{w['effect']:+.0f}"
        lines.append(f"  • {c['week']} {c['lane']} {c['kind']}: {c['pages']} page(s), pre {w['pre']} → post "
                     f"{w['post']}, site " + (f"×{w['control_ratio']:.2f}" if w["control_ratio"] else "n/a") + f", effect {eff}")
    if len(lines) == 1:
        lines.append("  (no mature cohort yet)")
    return lines


def digest_lines(since_days: int = 120) -> list[str]:
    """The digest section: the last 8 mature +28 d cohorts, and the JSON written to the runner's state dir."""
    since = (date.today() - timedelta(days=since_days)).isoformat()
    today = datetime.now(PACIFIC).date()
    rows = fetch_page_days((date.fromisoformat(since) - timedelta(days=28)).isoformat(), today.isoformat())
    cohorts = cohort_effects(changes_from_log(git_log(since)), page_days(rows), today)
    state = Path(os.environ.get("JR_STATE_DIR", Path.home() / ".local" / "state" / "espatlas-jr"))
    try:
        state.mkdir(parents=True, exist_ok=True)
        (state / f"outcomes-{today.isoformat()}.json").write_text(json.dumps(cohorts, default=str, indent=1))
    except OSError:
        pass
    lines = report_lines(cohorts)
    return lines[:1] + lines[1:][-8:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default=(date.today() - timedelta(days=120)).isoformat())
    args = ap.parse_args(argv)
    changes = changes_from_log(git_log(args.since))
    today = datetime.now(PACIFIC).date()
    rows = fetch_page_days((date.fromisoformat(args.since) - timedelta(days=28)).isoformat(), today.isoformat())
    cohorts = cohort_effects(changes, page_days(rows), today)
    print("\n".join(report_lines(cohorts)))
    state = Path(os.environ.get("JR_STATE_DIR", Path.home() / ".local" / "state" / "espatlas-jr"))
    state.mkdir(parents=True, exist_ok=True)
    (state / f"outcomes-{today.isoformat()}.json").write_text(json.dumps(cohorts, default=str, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
