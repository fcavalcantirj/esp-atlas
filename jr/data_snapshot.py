#!/usr/bin/env python3
"""Daily data-quality TREND row over both grounds (SPEC-data-trend.md).

The completion gauge (scripts/data_completion.py) is a SNAPSHOT of the finite ground; this module
records that snapshot once a day so its slope -- and the infinite ground's volume -- become
visible over time. Every finite number is REUSED from `compute_completion` (never recomputed);
the only numbers computed here are the INFINITE-ground volumes the gauge deliberately omits
(firmware + recipe counts) plus the SPINE coverage signals derived from them.

    python3 jr/data_snapshot.py --repo-root .                 # today (UTC)
    python3 jr/data_snapshot.py --repo-root . --date 2026-09-09

This is a REPORT, never a gate -- like data_completion it never affects scripts/validate.py's exit
code. It writes two files under docs/telemetry/: the append-only `data-trend.jsonl` history and a
human `data-<date>.md` snapshot with a Δ block vs the prior day. `build_row`/`write_snapshot` take
an explicit `date_str` and never read the clock (deterministic, testable); the clock lives only in
`main`. Tick-owned (jr/), so the `jr-tests` CI job covers it; distinct from jr/telemetry.py (the
GA4/GSC traffic job) -- the two never mix.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
REPO_ROOT = _JR_DIR.parent
_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import data_completion  # noqa: E402  (adds apps/core/src to sys.path on import)

# The four First-Flash board fields we trend, in report order. Each is a data_completion
# per_field label (scripts/data_completion.FIELD_SPECS["boards"]); pulled straight from the gauge.
BOARD_TREND_FIELDS = ("usb_serial", "getting_started", "download_mode", "pinout")

TELEMETRY_DIR = "docs/telemetry"
TREND_JSONL = f"{TELEMETRY_DIR}/data-trend.jsonl"


# --- the row --------------------------------------------------------------

def _count_files(data_dir: Path, pattern: str) -> int:
    return sum(1 for _ in data_dir.glob(pattern))


def _boards_with_firmware(data_dir: Path) -> int:
    """Distinct boards named in a recipe dir (`data/recipes/<board>__<firmware>/`)."""
    boards = set()
    for recipe in data_dir.glob("recipes/*/recipe.md"):
        name = recipe.parent.name
        if "__" in name:
            boards.add(name.split("__", 1)[0])
    return len(boards)


def _top_gap(gauge: dict) -> str:
    """The lowest-% finite field (with records) as '<entity>.<field> <pct>%'."""
    for g in gauge.get("gaps", []):
        if g.get("records", 0) > 0:
            return f"{g['entity']}.{g['field']} {g['pct']:g}%"
    return "none"


def _row_from_gauge(gauge: dict, data_dir: Path, date_str: str) -> dict:
    entities = gauge.get("entities", {})
    boards = entities.get("boards", {})
    per_field = boards.get("per_field", {})
    board_fields = {
        f: {"count": per_field.get(f, {}).get("count", 0), "pct": per_field.get(f, {}).get("pct", 0.0)}
        for f in BOARD_TREND_FIELDS
    }
    firmware_count = _count_files(data_dir, "firmware/*/firmware.md")
    recipe_count = _count_files(data_dir, "recipes/*/recipe.md")
    boards_total = boards.get("records", 0)
    with_fw = _boards_with_firmware(data_dir)
    return {
        "date": date_str,
        "finite_overall_pct": float(gauge.get("overall_pct", 0.0)),
        "boards_pct": float(boards.get("pct", 0.0)),
        "socs_pct": float(entities.get("socs", {}).get("pct", 0.0)),
        "modules_pct": float(entities.get("modules", {}).get("pct", 0.0)),
        "brands_pct": float(entities.get("brands", {}).get("pct", 0.0)),
        "board_fields": board_fields,
        "firmware_count": firmware_count,
        "recipe_count": recipe_count,
        "compat_density": round(recipe_count / firmware_count, 2) if firmware_count else 0.0,
        "boards_with_firmware": with_fw,
        "boards_zero_firmware": boards_total - with_fw,
        "top_gap": _top_gap(gauge),
    }


def build_row(data_dir, date_str: str) -> dict:
    """A single trend row for `date_str`, combining the reused finite gauge with the
    infinite-ground volume/coverage signals. Pure and deterministic (no clock)."""
    data_dir = Path(data_dir)
    gauge = data_completion.compute_completion(str(data_dir))
    return _row_from_gauge(gauge, data_dir, date_str)


# --- delta ----------------------------------------------------------------

def compute_delta(row: dict, prev: dict | None) -> dict | None:
    """Diff `row` against the immediately-prior row. None on the first snapshot."""
    if not prev:
        return None
    prev_fields = prev.get("board_fields", {})
    cur_fields = row.get("board_fields", {})
    return {
        "since": prev.get("date"),
        "finite_overall_pct": round(row["finite_overall_pct"] - prev.get("finite_overall_pct", 0.0), 1),
        "board_fields": {
            f: cur_fields.get(f, {}).get("count", 0) - prev_fields.get(f, {}).get("count", 0)
            for f in BOARD_TREND_FIELDS
        },
        "firmware_count": row["firmware_count"] - prev.get("firmware_count", 0),
        "recipe_count": row["recipe_count"] - prev.get("recipe_count", 0),
        "compat_density": round(row["compat_density"] - prev.get("compat_density", 0.0), 2),
    }


# --- jsonl history --------------------------------------------------------

def _read_rows(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.exists():
        return []
    rows = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("date"):
            rows.append(obj)
    return rows


def _merge_rows(rows: list[dict], row: dict) -> list[dict]:
    """Drop any existing row for this date, append, sort by date ascending. Idempotent."""
    kept = [r for r in rows if r.get("date") != row["date"]]
    kept.append(row)
    kept.sort(key=lambda r: r.get("date", ""))
    return kept


def _prev_row(rows: list[dict], date_str: str) -> dict | None:
    """The row with the greatest date strictly before `date_str`."""
    earlier = sorted((r for r in rows if r.get("date", "") < date_str), key=lambda r: r["date"])
    return earlier[-1] if earlier else None


# --- markdown snapshot ----------------------------------------------------

def _gauge_text(gauge: dict) -> str:
    """The compute_completion report, captured as text (reuses its own print_report)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        data_completion.print_report(gauge)
    return buf.getvalue().rstrip("\n")


def _sign(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def _signf(v: float, nd: int) -> str:
    return f"+{v:.{nd}f}" if v >= 0 else f"{v:.{nd}f}"


def _delta_block(row: dict, delta: dict | None) -> str:
    if delta is None:
        return "## Δ since —\n\nfirst snapshot — no baseline"
    lines = [f"## Δ since {delta['since']}", ""]
    lines.append(f"- finite_overall_pct: {row['finite_overall_pct']:g}% ({_signf(delta['finite_overall_pct'], 1)})")
    for f in BOARD_TREND_FIELDS:
        lines.append(f"- {f}: {row['board_fields'][f]['count']} ({_sign(delta['board_fields'][f])})")
    lines.append(f"- firmware_count: {row['firmware_count']} ({_sign(delta['firmware_count'])})")
    lines.append(f"- recipe_count: {row['recipe_count']} ({_sign(delta['recipe_count'])})")
    lines.append(f"- compat_density: {row['compat_density']:g} ({_signf(delta['compat_density'], 2)})")
    return "\n".join(lines)


def render_markdown(gauge: dict, row: dict, delta: dict | None) -> str:
    return (f"# esp-atlas data-quality snapshot — {row['date']}\n\n"
            f"```\n{_gauge_text(gauge)}\n```\n\n"
            f"{_delta_block(row, delta)}\n")


# --- write ----------------------------------------------------------------

def snapshot_paths(date_str: str) -> list[str]:
    """Repo-relative paths write_snapshot writes for `date_str` (for the tick's commit pathspec)."""
    return [TREND_JSONL, f"{TELEMETRY_DIR}/data-{date_str}.md"]


def write_snapshot(repo_root, date_str: str):
    """Write BOTH docs/telemetry outputs for `date_str` and return (row, delta).

    - Appends/replaces the row in data-trend.jsonl (one compact JSON object per line, sorted by
      date ascending); idempotent by date.
    - Writes data-<date>.md: the compute_completion report text + a Δ block vs the prior row.
    """
    repo_root = Path(repo_root)
    data_dir = repo_root / "data"
    gauge = data_completion.compute_completion(str(data_dir))
    row = _row_from_gauge(gauge, data_dir, date_str)

    out_dir = repo_root / TELEMETRY_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = repo_root / TREND_JSONL

    rows = _read_rows(jsonl_path)
    delta = compute_delta(row, _prev_row(rows, date_str))
    merged = _merge_rows(rows, row)
    body = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in merged)
    jsonl_path.write_text(body, encoding="utf-8")

    md_path = repo_root / f"{TELEMETRY_DIR}/data-{date_str}.md"
    md_path.write_text(render_markdown(gauge, row, delta), encoding="utf-8")
    return row, delta


# --- CLI ------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT),
                        help="repo root holding data/ and docs/ (defaults to this checkout)")
    parser.add_argument("--date", default=None,
                        help="the day to record, YYYY-MM-DD (defaults to today, UTC)")
    args = parser.parse_args(argv)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    row, delta = write_snapshot(args.repo_root, date_str)
    for p in snapshot_paths(date_str):
        print(f"wrote {p}")
    print(f"finite {row['finite_overall_pct']:g}% · firmware {row['firmware_count']} · "
          f"recipes {row['recipe_count']} · compat {row['compat_density']:g}/bd"
          + ("" if delta is None else f" (since {delta['since']})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
