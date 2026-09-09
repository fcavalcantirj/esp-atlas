"""EspAtlas Jr — demand STEER + supply×demand alignment (jr/demand_signal.py).

SPEC-demand-steering.md: read the latest committed demand snapshot (`docs/demand/<date>.json`,
mined READ-ONLY by jr/demand.py — never re-run here) and interpret it into (a) a small signed
`bias` that TILTS the allocator's A/B split toward unmet demand, and (b) a deterministic
alignment report for the tick's PR body.

THE STEERING RULE (SPEC-demand-steering.md):
  - **UNCOVERED demand is the ONLY authoring/steer signal.** An UNCOVERED item with a
    `firmware_token` (or a board+firmware pairing) is firmware/recipe demand → biases toward
    Track B (firmware). An UNCOVERED item resolving to a `part`/`chip`/`board` with no firmware
    angle is finite/board demand → biases toward Track A (backfill).
  - **RANKS_POORLY is a human SEO/content report, NEVER an authoring or allocation trigger** — it
    is surfaced in its own labelled report section and EXCLUDED from every steer bucket (matches
    demand.py's digest: "RANKS_POORLY — report for Felipe+us, never Jr's authoring path").
  - **COVERED_OK / UNRESOLVED are informational.**

The steer is a BIAS + a REPORT, never a gate: a missing snapshot (`load_latest` → None) or a
stale one (older than `stale_days`, default 14) yields NO steer — the allocator behaves exactly
as SPEC-data-completion.md defines today — and the report says so.

Pure functions, no I/O beyond `load_latest` reading `docs/demand/*.json`. No `datetime` except
the injected `today_str` (deterministic, testable). TILT_MAX is imported from jr/allocator.py so
the signal and the allocator's finite-floor clamp agree by construction.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from allocator import TILT_MAX  # single source of truth for the steer magnitude

DEFAULT_STALE_DAYS = 14

GAP_UNCOVERED = "UNCOVERED"
GAP_RANKS_POORLY = "RANKS_POORLY"
GAP_COVERED_OK = "COVERED_OK"
GAP_UNRESOLVED = "UNRESOLVED"
_GAP_CLASSES = (GAP_UNCOVERED, GAP_RANKS_POORLY, GAP_COVERED_OK, GAP_UNRESOLVED)


# ─────────────────────────── load the latest snapshot ───────────────────────────

def load_latest(demand_dir, today_str: str, stale_days: int = DEFAULT_STALE_DAYS) -> dict | None:
    """The newest `docs/demand/<date>.json` (ignoring `unresolved.json`), parsed, plus a
    computed `age_days` (days from its `date` to `today_str`) and `stale` flag
    (`age_days > stale_days`). None when the dir is missing/empty or nothing parses.

    Deterministic: the only clock is the injected `today_str`. `age_days` is derived from the
    snapshot's own `date` field, so a snapshot whose filename and body agree is dated exactly."""
    demand_dir = Path(demand_dir)
    if not demand_dir.exists():
        return None
    files = sorted(p for p in demand_dir.glob("*.json") if p.stem != "unresolved")
    if not files:
        return None
    try:
        snapshot = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(snapshot, dict) or not snapshot.get("date"):
        return None
    try:
        age_days = (dt.date.fromisoformat(today_str) - dt.date.fromisoformat(snapshot["date"])).days
    except (TypeError, ValueError):
        age_days = None
    snapshot["age_days"] = age_days
    snapshot["stale"] = age_days is None or age_days > stale_days
    return snapshot


# ─────────────────────────── steer signal (the bias) ───────────────────────────

def _has_firmware_angle(resolved: dict) -> bool:
    """Firmware/recipe demand: a resolved `firmware_token` (a board+firmware pairing carries the
    token too, so this one check covers both cases in SPEC-demand-steering.md)."""
    return bool(resolved.get("firmware_token"))


def _has_finite_angle(resolved: dict) -> bool:
    """Finite/board demand: a `part`/`chip`/`board` with no firmware angle."""
    return bool(resolved.get("part") or resolved.get("chip") or resolved.get("board"))


def _bucket_item(it: dict) -> dict:
    return {"term": it.get("term"), "weight": it.get("weight") or 0.0,
            "impressions": it.get("impressions"), "ctr": it.get("ctr"), "position": it.get("position"),
            "resolved": it.get("resolved") or {}}


def steer_signal(snapshot: dict) -> dict:
    """Interpret a snapshot into the steer buckets + a bounded signed `bias`.

    Only UNCOVERED items steer. Each UNCOVERED item goes to `uncovered_firmware` (has a
    firmware angle) or `uncovered_finite` (finite angle only); both are ranked by weight desc.
    `ranks_poorly` is the RANKS_POORLY SEO list (ranked by impressions) — reported, NEVER steered.

    `bias = TILT_MAX * (fw - fin) / (fw + fin)` over the two pools' summed weights: positive
    toward firmware (Track B), negative toward backfill (Track A), and exactly 0.0 when there is
    no UNCOVERED demand at all. Bounded to [-TILT_MAX, TILT_MAX] by construction."""
    items = snapshot.get("items") or []
    uncovered_firmware, uncovered_finite = [], []
    ranks_poorly = []
    for it in items:
        gap = it.get("gap")
        resolved = it.get("resolved") or {}
        if gap == GAP_UNCOVERED:
            if _has_firmware_angle(resolved):
                uncovered_firmware.append(_bucket_item(it))
            elif _has_finite_angle(resolved):
                uncovered_finite.append(_bucket_item(it))
        elif gap == GAP_RANKS_POORLY:
            ranks_poorly.append(_bucket_item(it))

    uncovered_firmware.sort(key=lambda b: b["weight"], reverse=True)
    uncovered_finite.sort(key=lambda b: b["weight"], reverse=True)
    ranks_poorly.sort(key=lambda b: (b.get("impressions") or 0), reverse=True)

    fw = sum(b["weight"] for b in uncovered_firmware)
    fin = sum(b["weight"] for b in uncovered_finite)
    total = fw + fin
    bias = round(TILT_MAX * (fw - fin) / total, 4) if total > 0 else 0.0

    return {"bias": bias, "uncovered_firmware": uncovered_firmware,
            "uncovered_finite": uncovered_finite, "ranks_poorly": ranks_poorly}


# ─────────────────────────── alignment report (supply × demand) ───────────────────────────

def alignment(snapshot: dict, supply_row: dict | None, top_n: int = 10) -> dict:
    """The supply×demand alignment report — deterministic weight math, no clock, no I/O.

    `aligned_pct` = share of total demand WEIGHT that is COVERED_OK (i.e. demand the atlas already
    serves), 0 when there is no weight. `counts` is the per-gap-class tally. `demanded_but_missing`
    is the worklist: UNCOVERED first (Jr's authoring path), then RANKS_POORLY (the human SEO list),
    each ranked by weight, capped at `top_n`. `supply_row` (the SPEC-data-trend.md row, or None)
    rides along for the report's supply context."""
    items = snapshot.get("items") or []
    counts = {g: 0 for g in _GAP_CLASSES}
    total_weight = 0.0
    covered_weight = 0.0
    for it in items:
        gap = it.get("gap")
        w = it.get("weight") or 0.0
        total_weight += w
        if gap in counts:
            counts[gap] += 1
        if gap == GAP_COVERED_OK:
            covered_weight += w

    aligned_pct = round(covered_weight / total_weight * 100) if total_weight > 0 else 0

    missing = [it for it in items if it.get("gap") in (GAP_UNCOVERED, GAP_RANKS_POORLY)]
    # UNCOVERED before RANKS_POORLY, each by weight desc — deterministic ordering
    missing.sort(key=lambda it: (0 if it.get("gap") == GAP_UNCOVERED else 1, -(it.get("weight") or 0.0)))
    demanded_but_missing = [
        {"term": it.get("term"), "gap": it.get("gap"), "weight": it.get("weight") or 0.0,
         "impressions": it.get("impressions"), "ctr": it.get("ctr"), "position": it.get("position"),
         "resolved": it.get("resolved") or {}}
        for it in missing[:top_n]
    ]

    supply = None
    if supply_row:
        supply = {"finite_overall_pct": supply_row.get("finite_overall_pct"),
                  "firmware_count": supply_row.get("firmware_count")}

    return {"aligned_pct": aligned_pct, "counts": counts, "uncovered": counts[GAP_UNCOVERED],
            "total_weight": round(total_weight, 2), "demanded_but_missing": demanded_but_missing,
            "supply": supply}
