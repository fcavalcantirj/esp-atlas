"""EspAtlas Jr — the yield ledger (jr/yield_ledger.py, SPEC-data-completion.md "Yield").

One row per content stage per tick in `docs/telemetry/yield.jsonl` (an AUTO bookkeeping path, like
`data-trend.jsonl`): what the stage was given (units) and what it produced (records, recipes, filled
fields), with the tick's budget spend beside it. The allocator reads the trailing window per LANE —
backfill = Track A, firmware = admit + boardmap (Track B), topics outside the split — and a lane that
produced nothing over a full window while the other produced gives its units up to the floor. The same
rows are the evidence a stall incident (SPEC-jr-self-heal.md) hands the coding agent.

Measured before this existed (160 tick PRs, 2026-11-10 → 11-17): backfill produced 0 in 160/160 ticks on
3 units an hour (480 units); firmware produced in 24/160 ticks, normal gaps 1–4 ticks, and a 51-tick
zero streak (Nov 15 21Z → Nov 17 23Z) that nothing noticed. Append-only, idempotent per (tick, stage).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pending_prs

RELPATH = "docs/telemetry/yield.jsonl"
LANES = {"backfill": ("backfill",), "firmware": ("admit", "boardmap"), "topics": ("admit_topics",)}
SPLIT_LANES = ("backfill", "firmware")        # the two the allocator splits; topics is fixed


def tick_stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")


def rows_for_tick(stages: list[dict], split: dict, now: datetime, calls: int | None = None,
                  seconds: float | None = None, units_topics: int = 0) -> list[dict]:
    """One row per content stage this tick ran (stages = the report's stage dicts). `split` gives the
    units backfill/admit/boardmap received; a stage absent from the tick writes no row."""
    stamp = tick_stamp(now)
    fw = int(split.get("firmware") or 0)
    adm = fw // 2
    units = {"backfill": int(split.get("backfill") or 0), "admit": adm, "boardmap": fw - adm,
             "admit_topics": int(units_topics)}
    rows = []
    for s in stages:
        name = s.get("name")
        if name not in units:
            continue
        produced = int(s.get("produced") or 0)
        rows.append({"tick": stamp, "stage": name, "units": units[name], "produced": produced,
                     "paths": len(s.get("paths") or []), "counts": dict(s.get("counts") or {}),
                     "calls": calls, "seconds": None if seconds is None else round(float(seconds), 1)})
    return rows


def read_rows(path: Path) -> list[dict]:
    """Every well-formed row, in file order; a corrupt line is skipped, never fatal."""
    p = Path(path)
    return parse_rows(p.read_text(encoding="utf-8")) if p.is_file() else []


def parse_rows(text: str | None) -> list[dict]:
    """Every well-formed row of a yield.jsonl text, in order; a corrupt line is skipped."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tick"), str) and isinstance(obj.get("stage"), str):
            rows.append(obj)
    return rows


def append_rows(path: Path, rows: list[dict]) -> list[dict]:
    """Write `rows`, replacing any existing row for the same (tick, stage); the file stays sorted by
    tick then stage. Returns the rows now in the file."""
    p = Path(path)
    keys = {(r["tick"], r["stage"]) for r in rows}
    kept = [r for r in read_rows(p) if (r["tick"], r["stage"]) not in keys] + list(rows)
    kept.sort(key=lambda r: (r["tick"], r["stage"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(_render(kept), encoding="utf-8")
    tmp.replace(p)
    return kept


def rows_missing(have: list[dict], other: list[dict]) -> list[dict]:
    """The rows of `other` whose (tick, stage) `have` lacks, first copy wins: what an open tick PR wrote
    that main never received (a producing tick's PR waits for review, so its row is not on main)."""
    keys, out = {(r["tick"], r["stage"]) for r in have}, []
    for r in other:
        if (r["tick"], r["stage"]) not in keys:
            keys.add((r["tick"], r["stage"]))
            out.append(r)
    return out


def open_pr_rows(gh, slug: str, prs: list) -> tuple[list[dict], list[str]]:
    """([rows], warnings): the yield rows each eligible open tick PR committed, read raw at its pinned head
    (headRefOid), one call per PR and only for a PR that changes this ledger. A producing tick opens a
    jr-review PR and its row waits there for the owner, so main's ledger alone shows only the silent ticks
    (2026-11-19, stall:topics: 0/48u while #1828, #1875 and #1895 had authored 4 records). Best-effort:
    an unreadable copy is a warning, never an abort."""
    rows, warnings = [], []
    for pr in sorted((pr for pr in prs if pending_prs.eligible(pr)), key=lambda pr: pr.get("number") or 0):
        n, oid = pr.get("number"), pr.get("headRefOid")
        if RELPATH not in [f.get("path") for f in (pr.get("files") or []) if isinstance(f, dict)]:
            continue
        try:
            if not slug or not isinstance(oid, str) or not oid:
                raise ValueError("no pinned head")
            p = gh("api", "-H", pending_prs.RAW_MEDIA, f"repos/{slug}/contents/{RELPATH}?ref={oid}")
            if getattr(p, "returncode", 1) != 0:
                raise ValueError("gh api failed")
            rows += rows_missing(rows, parse_rows(getattr(p, "stdout", "")))
        except Exception as e:  # noqa: BLE001 — one PR's copy must never abort the tick
            warnings.append(f"open-PR yield rows from #{n} unreadable: {type(e).__name__}: {e}")
    return rows, warnings


def merge_text(main: str, pr: str) -> str:
    """The yield.jsonl a PR refreshed against main carries (jr/review_refresh.py): main's rows plus every
    PR row main lacks — the PR's own tick — keyed by (tick, stage), main's row on a shared key, sorted.
    Taking main's file alone erased the producing ticks' rows (incident 0cf1acb95f79, 2026-11-19)."""
    rows = {(r["tick"], r["stage"]): r for r in parse_rows(pr)}
    rows.update({(r["tick"], r["stage"]): r for r in parse_rows(main)})
    return _render([rows[k] for k in sorted(rows)])


def _render(rows: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)


def lane_yield(rows: list[dict], now: datetime, window_ticks: int) -> dict:
    """Per lane over the `window_ticks` most recent distinct ticks BEFORE this one: ticks in which the
    lane had units, the units, and what it produced. A lane absent from a tick (no units) is not
    counted for that tick, so a lane parked at zero units can never look 'dead'."""
    stamp = tick_stamp(now)
    ticks = sorted({r["tick"] for r in rows if r["tick"] < stamp})[-max(0, int(window_ticks)):]
    window = set(ticks)
    out = {}
    for lane, names in LANES.items():
        seen, units, produced = set(), 0, 0
        for r in rows:
            if r["tick"] in window and r["stage"] in names and int(r.get("units") or 0) > 0:
                seen.add(r["tick"])
                units += int(r.get("units") or 0)
                produced += int(r.get("produced") or 0)
        out[lane] = {"ticks": len(seen), "units": units, "produced": produced}
    out["window_ticks"] = int(window_ticks)
    out["ticks_in_window"] = len(window)
    return out


def dead_lanes(yields: dict, window_ticks: int) -> list[str]:
    """The split lanes observed over a full window that produced nothing while the other produced."""
    full = {lane for lane in SPLIT_LANES if yields.get(lane, {}).get("ticks", 0) >= window_ticks}
    produced = {lane: yields.get(lane, {}).get("produced", 0) for lane in SPLIT_LANES}
    if not any(produced.values()):
        return []                         # both silent: the split cannot know which to favour (a stall, not a tilt)
    return [lane for lane in SPLIT_LANES if lane in full and produced[lane] == 0]


def stalled_lanes(yields: dict, stall_ticks: int) -> list[str]:
    """Every lane (topics included) observed over `stall_ticks` ticks with nothing produced."""
    return [lane for lane in LANES if yields.get(lane, {}).get("ticks", 0) >= stall_ticks
            and yields.get(lane, {}).get("produced", 0) == 0]


def summary(yields: dict) -> str:
    """`yield backfill 0/72u firmware 3/72u topics 0/48u (24 ticks)`: produced over units per lane."""
    parts = [f"{lane} {yields.get(lane, {}).get('produced', 0)}/{yields.get(lane, {}).get('units', 0)}u" for lane in LANES]
    return "yield " + " ".join(parts) + f" ({yields.get('ticks_in_window', 0)} ticks)"
