"""EspAtlas Jr — the board-universe manifest loader + the honest coverage denominator
(SPEC-universe.md).

esp-atlas's live gauge reports completion as *cataloged ÷ what-we-have*, so it can never
fall below what we already shipped — it lies about how much of the real ESP32 board
universe is missing. This module supplies the FOUNDATION for an honest denominator:

- `load_universe(docs_dir)` parses the committed `docs/universe/<brand>.yaml` manifests
  into `{brand: [entries]}`.
- `coverage(universe, boards_root)` computes *cataloged ÷ universe*, per-brand and overall,
  where **cataloged is DERIVED** by checking whether
  `data/boards/<brand>/<board_id>/board.md` exists on disk. There is no stored `in_catalog`
  flag; the filesystem is the single source of truth.
- `render_coverage_md(cov)` renders the real gauge as markdown.

**READ-ONLY. NO NETWORK. NO WRITES TO data/.** This module only reads the committed
manifests and the `data/boards/` filesystem. The manifest is built OFFLINE and committed
(same pattern as `docs/demand/`); nothing here — and nothing in tick/allocator/CI — fetches
it. This slice must not change tick/allocator behavior.

Run tests:  cd jr && python3 -m pytest test_universe.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

JR_DIR = Path(__file__).resolve().parent
REPO = JR_DIR.parent
UNIVERSE_DIR = REPO / "docs" / "universe"
BOARDS_ROOT = REPO / "data" / "boards"

VALID_STATUS = ("active", "discontinued")

# Files under docs/universe/ that are NOT brand manifests (the rendered report, notes, …).
_NON_MANIFEST_STEMS = frozenset({"coverage"})


class ManifestError(ValueError):
    """A manifest file is malformed or an entry violates SPEC-universe.md."""


# ─────────────────────────────── loading / parsing ───────────────────────────────

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ManifestError(msg)


def _parse_entry(raw: Any, *, brand: str, seen_ids: set[str]) -> dict:
    """Validate and normalize one board entry. Raises ManifestError on anything malformed.

    Cite-or-omit is enforced structurally here: an entry with no non-empty `source_url`
    is a hard error, never silently dropped — the manifest author must omit it upstream."""
    _require(isinstance(raw, dict), f"{brand}: board entry is not a mapping: {raw!r}")

    board_id = raw.get("board_id")
    _require(isinstance(board_id, str) and board_id.strip(),
             f"{brand}: entry missing a non-empty board_id: {raw!r}")
    board_id = board_id.strip()
    _require(board_id not in seen_ids, f"{brand}: duplicate board_id {board_id!r}")

    name = raw.get("name")
    _require(isinstance(name, str) and name.strip(),
             f"{brand}/{board_id}: missing a non-empty name")

    mcu = raw.get("mcu")
    _require(isinstance(mcu, str) and mcu.strip(),
             f"{brand}/{board_id}: missing a non-empty mcu")

    source_url = raw.get("source_url")
    _require(isinstance(source_url, str) and source_url.strip(),
             f"{brand}/{board_id}: missing source_url (cite-or-omit — no entry without a real source)")

    status = raw.get("status")
    _require(status in VALID_STATUS,
             f"{brand}/{board_id}: status must be one of {VALID_STATUS}, got {status!r}")

    entry = {
        "board_id": board_id,
        "name": name.strip(),
        "mcu": mcu.strip(),
        "source_url": source_url.strip(),
        "status": status,
        "brand": brand,
    }
    note = raw.get("note")
    if note is not None:
        _require(isinstance(note, str), f"{brand}/{board_id}: note must be a string")
        entry["note"] = note.strip()
    seen_ids.add(board_id)
    return entry


def load_manifest(path: str | Path) -> list[dict]:
    """Load and validate a single brand manifest, returning its list of board entries.

    Raises ManifestError if the file is not valid YAML, is not a mapping, is missing/empty
    `brand` or `boards`, or if any entry is malformed."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:  # pragma: no cover - message varies by pyyaml version
        raise ManifestError(f"{path.name}: invalid YAML: {e}") from e

    _require(isinstance(doc, dict), f"{path.name}: top-level document is not a mapping")
    brand = doc.get("brand")
    _require(isinstance(brand, str) and brand.strip(), f"{path.name}: missing a non-empty 'brand'")
    brand = brand.strip()

    boards = doc.get("boards")
    _require(isinstance(boards, list) and boards, f"{path.name}: 'boards' must be a non-empty list")

    seen_ids: set[str] = set()
    return [_parse_entry(raw, brand=brand, seen_ids=seen_ids) for raw in boards]


def load_universe(docs_dir: str | Path = UNIVERSE_DIR) -> dict[str, list[dict]]:
    """Load every brand manifest under `docs_dir` into `{brand: [entries]}`.

    Reads `docs/universe/<brand>.yaml` only (the rendered `coverage.md` and any non-manifest
    files are ignored). No network, no writes. Sorted by brand for deterministic output."""
    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        return {}

    universe: dict[str, list[dict]] = {}
    for path in sorted(docs_dir.glob("*.yaml")):
        if path.stem in _NON_MANIFEST_STEMS:
            continue
        entries = load_manifest(path)
        brand = entries[0]["brand"]
        _require(brand not in universe, f"duplicate brand manifest for {brand!r} ({path.name})")
        universe[brand] = entries
    return dict(sorted(universe.items()))


# ─────────────────────────── coverage (the honest denominator) ───────────────────────────

def is_cataloged(brand: str, board_id: str, boards_root: str | Path = BOARDS_ROOT) -> bool:
    """DERIVED catalog check: True iff data/boards/<brand>/<board_id>/board.md exists.

    Never trusts a stored flag — the filesystem is the single source of truth."""
    return (Path(boards_root) / brand / board_id / "board.md").is_file()


def coverage(universe: dict[str, list[dict]],
             boards_root: str | Path = BOARDS_ROOT) -> dict:
    """Compute the honest gauge: cataloged ÷ universe, per-brand and overall.

    `cataloged` is DERIVED per board via `is_cataloged` (board.md existence) — never stored.
    Returns::

        {
          "brands": {
            <brand>: {"universe_count": int, "cataloged_count": int, "missing": [board_id, ...]},
            ...
          },
          "overall": {"universe_count": int, "cataloged_count": int,
                       "missing_count": int, "pct": float},
        }

    `pct` is cataloged/universe*100 rounded to one decimal (0.0 when the universe is empty).
    `missing` lists, in manifest order, every board_id with no board.md."""
    brands: dict[str, dict] = {}
    total_universe = 0
    total_cataloged = 0

    for brand, entries in universe.items():
        missing: list[str] = []
        cataloged = 0
        for entry in entries:
            if is_cataloged(brand, entry["board_id"], boards_root):
                cataloged += 1
            else:
                missing.append(entry["board_id"])
        brands[brand] = {
            "universe_count": len(entries),
            "cataloged_count": cataloged,
            "missing": missing,
        }
        total_universe += len(entries)
        total_cataloged += cataloged

    pct = round(total_cataloged / total_universe * 100, 1) if total_universe else 0.0
    return {
        "brands": brands,
        "overall": {
            "universe_count": total_universe,
            "cataloged_count": total_cataloged,
            "missing_count": total_universe - total_cataloged,
            "pct": pct,
        },
    }


def _pct(cataloged: int, universe: int) -> float:
    return round(cataloged / universe * 100, 1) if universe else 0.0


def render_coverage_md(cov: dict) -> str:
    """Render the honest coverage gauge (SPEC-universe.md deliverable #4) as markdown.

    Pure function over a `coverage()` result — no I/O."""
    ov = cov["overall"]
    lines: list[str] = [
        "# ESP32 Board Universe — Real Coverage",
        "",
        "> The honest denominator: **cataloged ÷ universe**, not cataloged ÷ what-we-have.",
        "> Generated from `docs/universe/<brand>.yaml` (built offline, committed) and the",
        "> derived catalog check (`data/boards/<brand>/<board_id>/board.md` existence).",
        "> This is a report only — it does NOT feed the live tick gauge or allocator.",
        "",
        f"**Overall: {ov['cataloged_count']}/{ov['universe_count']} boards cataloged "
        f"({ov['pct']}%) — {ov['missing_count']} missing.**",
        "",
        "| Brand | Cataloged | Universe | % | Missing board_ids |",
        "| --- | --- | --- | --- | --- |",
    ]
    for brand in sorted(cov["brands"]):
        b = cov["brands"][brand]
        missing = ", ".join(f"`{m}`" for m in b["missing"]) if b["missing"] else "—"
        lines.append(
            f"| {brand} | {b['cataloged_count']} | {b['universe_count']} | "
            f"{_pct(b['cataloged_count'], b['universe_count'])}% | {missing} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual/offline render helper
    cov = coverage(load_universe())
    print(render_coverage_md(cov))
