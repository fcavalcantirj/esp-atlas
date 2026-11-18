"""EspAtlas Jr — the daily resolver report (jr/resolver_run.py), the resolver class's source.

The model boundary (CLAUDE.md "North star"): an LLM solves CODE problems, never fills inventory. So the
gauge's gaps do not become "fill field X on board Y" items; they become "write the deterministic extractor
for vendor V × field X" items, and the hourly backfill then fills every such board itself, reproducibly,
forever. This module ranks the gaps: per vendor × field, the boards of that vendor missing the field
(`scripts/data_completion.per_vendor`), ordered by boards missing, then by PAGE DEMAND as the tie-breaker
(GSC impressions of those boards' own `/parts/<id>` pages in the latest demand snapshot, and whether any
ranks poorly; owner 2026-11-17: demand may ORDER data work, never touch SEO text), then vendor and field.

Rows need at least MIN_MISSING boards (a resolver for one board is not worth a delegate run; the closure
needs min(3, expected) boards to gain the field). Like the PAM and quote sources: the report lands only when
its rows changed; it is always `complete` (no network); any error defers and the previous report stays.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import demand_signal  # noqa: E402

STATE_PATH = "docs/demand/resolver-report.json"
MIN_MISSING = 3
MAX_BOARDS_LISTED = 40          # every missing board of the vendor, capped: the executor's expected ids


@dataclass
class RefreshResult:
    status: str                      # updated | unchanged | deferred
    changed_paths: tuple = ()
    error: str = ""
    counts: dict = field(default_factory=dict)
    complete: bool = True

    def report(self) -> dict:
        return {"status": self.status, "changed_paths": list(self.changed_paths), "error": self.error,
                "counts": dict(self.counts), "complete": self.complete}


def page_demand(snap: dict | None) -> dict:
    """board id -> {"impressions": n, "ranks_poorly": bool} from a demand snapshot's landing pages."""
    out: dict = {}
    for item in (snap or {}).get("items") or []:
        page = item.get("landing_page") if isinstance(item, dict) else None
        if not isinstance(page, str) or "/parts/" not in page:
            continue
        board = page.rsplit("/parts/", 1)[1].split("/")[0].split("?")[0].split("#")[0]
        if not board:
            continue
        d = out.setdefault(board, {"impressions": 0, "ranks_poorly": False})
        d["impressions"] += int(item.get("impressions") or 0)
        d["ranks_poorly"] = d["ranks_poorly"] or item.get("gap") == "RANKS_POORLY"
    return out


def rank_gaps(per_vendor: dict, demand: dict, *, min_missing: int = MIN_MISSING) -> list[dict]:
    """The report rows: one per vendor × field with >= min_missing boards missing, ordered by boards
    missing (desc), page impressions of those boards (desc), vendor, field."""
    rows = []
    for vendor, v in (per_vendor.get("vendors") or {}).items():
        for fld, info in (v.get("fields") or {}).items():
            boards = list(info.get("boards") or [])
            if len(boards) < min_missing:
                continue
            imps = sum(demand.get(b, {}).get("impressions", 0) for b in boards)
            poorly = sum(1 for b in boards if demand.get(b, {}).get("ranks_poorly"))
            rows.append({"vendor": vendor, "field": fld, "missing": len(boards), "records": int(v.get("records") or 0),
                         "boards": boards[:MAX_BOARDS_LISTED], "demand_impressions": imps, "ranks_poorly": poorly})
    rows.sort(key=lambda r: (-r["missing"], -r["demand_impressions"], -r["ranks_poorly"], r["vendor"], r["field"]))
    return rows


def _comparable(doc: dict | None) -> list:
    if not isinstance(doc, dict):
        return []
    return [(r.get("vendor"), r.get("field"), r.get("missing"), tuple(r.get("boards") or []))
            for r in doc.get("records") or [] if isinstance(r, dict)]


def build_report(wt_path: Path, *, today: str, snap: dict | None = None) -> dict:
    import data_completion
    pv = data_completion.per_vendor(str(Path(wt_path) / "data"))
    rows = rank_gaps(pv, page_demand(snap))
    return {"version": 1, "date": today, "complete": True, "records": rows,
            "counts": {"vendors": len(pv.get("vendors") or {}), "gaps": len(rows),
                       "boards_missing_total": sum(r["missing"] for r in rows)}}


def refresh_worktree(wt_path: Path, *, now: datetime, snap: dict | None = None) -> RefreshResult:
    """Write the day's report into the worktree (or leave it) and say what changed. `snap` is the demand
    snapshot whose landing pages order ties (default: the worktree's latest dated snapshot, if any)."""
    today = now.astimezone(timezone.utc).date().isoformat()
    target = Path(wt_path) / STATE_PATH
    try:
        previous = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else None
    except (OSError, json.JSONDecodeError):
        previous = None
    try:
        if snap is None:
            try:
                snap = demand_signal.load_latest(Path(wt_path), today)
            except Exception:  # noqa: BLE001 — no snapshot: ties fall back to vendor/field order
                snap = None
        doc = build_report(wt_path, today=today, snap=snap)
    except Exception as e:  # noqa: BLE001
        return RefreshResult("deferred", error=f"{type(e).__name__}: {e}")
    counts = dict(doc["counts"])
    if _comparable(previous) == _comparable(doc):
        return RefreshResult("unchanged", counts=counts)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return RefreshResult("updated", changed_paths=(STATE_PATH,), counts=counts)
