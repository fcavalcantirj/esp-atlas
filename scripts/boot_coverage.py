#!/usr/bin/env python3
"""Jr backfill worklist: every board missing `download_mode` and/or `usb_serial`
(SPEC-first-flash.md P0/P3). Both fields stay OPTIONAL in schema/board.schema.json
for now -- 82 of 199 boards predate this data -- so this is a report, never a gate.
scripts/validate.py stays the deterministic CI gate; this script never affects
its exit code and never fails the build.

    python3 scripts/boot_coverage.py

Maps to `npm run boot:coverage`.
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

BOOT_FIELDS = ("download_mode", "usb_serial")


def iter_board_files(data_dir):
    """Yield every data/boards/<brand>/<id>/board.md Path under `data_dir`,
    sorted for deterministic report ordering."""
    return sorted(Path(data_dir).glob(DATA_PATTERNS["board"]))


def check_board(path):
    """Parse one board.md and return an entry ({id, brand, path, missing_fields})
    if it's missing download_mode and/or usb_serial, else None."""
    fm, _body = parse_frontmatter(path)
    missing_fields = [field for field in BOOT_FIELDS if not fm.get(field)]
    if not missing_fields:
        return None
    return {
        "id": fm.get("id") or path.parent.name,
        "brand": fm.get("brand") or path.parent.parent.name,
        "path": path,
        "missing_fields": missing_fields,
    }


def run(data_dir=None):
    """Scan every board under `data_dir` (defaults to data/) and return a report
    dict: {missing: [...], total: int}. Never signals failure -- see module docstring."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    paths = iter_board_files(root)
    missing = [entry for entry in (check_board(p) for p in paths) if entry]
    return {"missing": missing, "total": len(paths)}


def print_report(report):
    missing = report["missing"]
    print(f"BOOT-MODE COVERAGE: {report['total'] - len(missing)}/{report['total']} boards have both fields\n")
    if not missing:
        print("  none missing -- worklist is empty")
    for entry in missing:
        try:
            rel = entry["path"].relative_to(REPO_ROOT)
        except ValueError:
            rel = entry["path"]
        print(f"  ⚠ {entry['brand']}/{entry['id']}: missing {', '.join(entry['missing_fields'])} ({rel})")
    print(f"\n{len(missing)} board(s) on the backfill worklist")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                         help="override the data/ root to scan (mainly for tests); "
                              "defaults to <repo root>/data")
    args = parser.parse_args(argv)

    report = run(args.data_dir)
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
