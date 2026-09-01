#!/usr/bin/env python3
"""Data-completion gauge over the FINITE ground (SPEC-data-completion.md).

The finite ground -- socs, modules, boards, brands -- is a *knowable, bounded*
set that can reach 100%. This gauge measures how complete that foundation is,
per entity type and per "usefulness field", and folds it into a single
board-weighted OVERALL FINITE-COMPLETION %. That number drives Jr's Track-A vs
Track-B allocation, and the lowest-% fields double as the Track-A backlog.

Firmware and recipes are the INFINITE ground (never "done") and are deliberately
NOT measured here.

    python3 scripts/data_completion.py            # gauge the real data/ dir
    python3 scripts/data_completion.py --data-dir /tmp/fixture

Maps to `npm run data:completion`. Reuses scripts/boot_coverage.py's board
frontmatter-reading patterns (esp_atlas_core.frontmatter). This is a REPORT,
never a gate -- scripts/validate.py stays the deterministic CI gate; this script
never affects its exit code.

v1 measures PRESENCE only -- a field counts as complete when it is present and
non-empty in the frontmatter. Per-field *citation*-completeness (cite-or-omit,
cross-checking data/**/sources) is a future refinement noted in the spec's
"What counts as complete" section; it is intentionally out of scope for v1.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402

# --- weights --------------------------------------------------------------
# Boards dominate: they are what First-Flash needs, so their completion carries
# half the overall gauge. socs/modules/brands split the rest. Tunable here.
WEIGHTS = {
    "boards": 0.5,
    "socs": 0.2,
    "modules": 0.15,
    "brands": 0.15,
}

# --- usefulness fields ----------------------------------------------------
# Each entry: (report_label, dotted frontmatter path). Presence of the value at
# that path (non-empty) counts the record as complete for that field.
#
# Derivation (SPEC-data-completion.md "What counts as complete"):
#   * boards: the First-Flash + physical-identity fields. `getting_started`
#     does NOT exist in the schema yet (field-to-add) -> counts as missing
#     everywhere until it lands, which is the intended signal.
#   * socs: the datasheet key specs from schema/soc.schema.json `required`
#     (cpu, memory, radios) plus the "if present" hardware keys the schema
#     models (gpio pad count, native-usb).
#   * modules: the module-specific specs from schema/module.schema.json
#     `required` link (soc) plus flash / psram / antenna / certs. cpu/ram/radio
#     are inherited from the soc and deliberately NOT restated here.
#   * brands: homepage url (schema `required`).
FIELD_SPECS = {
    "boards": [
        ("download_mode", "download_mode"),
        ("usb_serial", "usb_serial"),
        ("pinout", "io.gpio_pins"),
        ("dimensions_mm", "dimensions_mm"),
        ("form_factor", "form_factor"),
        ("usb_connector", "usb.connector"),
        ("getting_started", "getting_started"),
    ],
    "socs": [
        ("cpu_cores", "cpu.cores"),
        ("ram", "memory.sram_kb"),
        ("radios", "radios"),
        ("gpio_count", "drive.gpio_pads_total"),
        ("native_usb", "usb.native"),
    ],
    "modules": [
        ("soc_link", "soc"),
        ("flash", "flash_mb"),
        ("psram", "psram_mb"),
        ("antenna", "antenna"),
        ("certs", "certifications"),
    ],
    "brands": [
        ("homepage", "url"),
    ],
}

# report label (plural) -> DATA_PATTERNS key (singular)
_PATTERN_KEY = {
    "boards": "board",
    "socs": "soc",
    "modules": "module",
    "brands": "brand",
}


def _get_nested(fm, dotted):
    """Walk a dotted path (e.g. 'io.gpio_pins') through nested dicts; return the
    value or None if any level is missing / not a dict."""
    cur = fm
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_present(value):
    """A field counts as complete when it is present and non-empty. Booleans
    (incl. False) and 0 count as ANSWERED specs -- e.g. usb.native: false is a
    real, verified answer, not a gap."""
    if value is None:
        return False
    if isinstance(value, (str, list, dict)):
        return len(value) > 0
    return True


def _iter_records(data_dir, entity):
    """Yield frontmatter dicts for every record of one entity type under
    data_dir. Skips files that fail to parse (never crashes the gauge)."""
    pattern = DATA_PATTERNS[_PATTERN_KEY[entity]]
    for path in sorted(Path(data_dir).glob(pattern)):
        try:
            fm, _body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if isinstance(fm, dict):
            yield fm


def _pct(count, total):
    return round(count / total * 100.0, 1) if total else 0.0


def compute_completion(data_dir=None):
    """Measure finite-ground completion. Returns a reusable dict:

        {
          "entities": {
            "<entity>": {
              "records": int,
              "per_field": {"<label>": {"count": int, "pct": float}, ...},
              "pct": float,          # mean of this entity's per-field pcts
            }, ...
          },
          "overall_pct": float,      # board-weighted mean across entity types
          "weights": {...},
          "gaps": [                  # lowest-% fields first (Track-A backlog)
            {"entity", "field", "count", "records", "pct"}, ...
          ],
        }

    Intended for reuse by telemetry / the /status page; the CLI just prints it.
    """
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    entities = {}
    gaps = []

    for entity, fields in FIELD_SPECS.items():
        records = list(_iter_records(root, entity))
        n = len(records)
        per_field = {}
        for label, dotted in fields:
            count = sum(1 for fm in records if _is_present(_get_nested(fm, dotted)))
            per_field[label] = {"count": count, "pct": _pct(count, n)}
            gaps.append({
                "entity": entity,
                "field": label,
                "count": count,
                "records": n,
                "pct": _pct(count, n),
            })
        entity_pct = round(sum(f["pct"] for f in per_field.values()) / len(per_field), 1) if per_field else 0.0
        entities[entity] = {"records": n, "per_field": per_field, "pct": entity_pct}

    total_weight = sum(WEIGHTS[e] for e in FIELD_SPECS)
    overall = sum(WEIGHTS[e] * entities[e]["pct"] for e in FIELD_SPECS) / total_weight if total_weight else 0.0

    # Lowest completion first; stable tiebreak by entity/field for determinism.
    gaps.sort(key=lambda g: (g["pct"], g["entity"], g["field"]))

    return {
        "entities": entities,
        "overall_pct": round(overall, 1),
        "weights": dict(WEIGHTS),
        "gaps": gaps,
    }


def print_report(report, gaps_limit=8):
    print("FINITE-GROUND DATA-COMPLETION GAUGE (presence, v1)\n")
    for entity, data in report["entities"].items():
        n = data["records"]
        weight = report["weights"].get(entity, 0.0)
        parts = [
            f"{label} {stats['count']}/{n} {stats['pct']:g}%"
            for label, stats in data["per_field"].items()
        ]
        print(f"{entity} ({n})  [weight {weight:g}]  overall {data['pct']:g}%")
        print("    " + " · ".join(parts))
        print()

    print(f"OVERALL FINITE-COMPLETION: {report['overall_pct']:g}%  "
          f"(board-weighted mean across entity types)\n")

    # Biggest gaps == the Track-A backlog. Skip entity types with no records.
    worklist = [g for g in report["gaps"] if g["records"] > 0][:gaps_limit]
    print(f"BIGGEST GAPS (Track-A worklist, lowest % first):")
    if not worklist:
        print("    none -- no records to measure")
    for g in worklist:
        print(f"    {g['entity']}.{g['field']}: {g['count']}/{g['records']} {g['pct']:g}%")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ root to scan (mainly for tests); "
                             "defaults to <repo root>/data")
    args = parser.parse_args(argv)

    report = compute_completion(args.data_dir)
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
