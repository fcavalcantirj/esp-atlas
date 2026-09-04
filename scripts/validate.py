#!/usr/bin/env python3
"""Validate every data/**/*.md frontmatter against schema/<type>.schema.json.

The correctness gate for esp-atlas. CI runs this on every PR; a spec change with
no matching source entry, or any schema violation, fails the build. Run locally:

    python3 scripts/validate.py

All the actual rule-checking (JSON Schema, source-or-omit, id/brand-vs-folder,
inheritance refs) lives in esp_atlas_core.validate so this script, the
`esp-atlas validate` CLI command, and the API's POST /validate stay in sync.

Also mechanically enforces the firmware popularity floor (SPEC-firmware-floor.md: GitHub
stars >= 25 OR forks >= 25, downloads are not a signal) via check_popularity_floor() below,
which reuses firmware_floor_audit.audit() (same directory) so the floor definition lives in
exactly one place. This makes the floor a validation-time gate, not just a drain-time one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "core" / "src"))

from esp_atlas_core.frontmatter import iter_data_files  # noqa: E402
from esp_atlas_core.paths import REPO_ROOT  # noqa: E402
from esp_atlas_core.validate import check_orphan_firmware, known_ids, validate_file  # noqa: E402

import firmware_floor_audit  # noqa: E402


def check_popularity_floor(data_dir=None):
    """Mechanical enforcement of SPEC-firmware-floor.md at validation time: FAILS for every
    non-curated-exempt firmware entry below BOTH floors (stars < STAR_FLOOR AND
    forks < FORK_FLOOR). Reuses firmware_floor_audit.audit() so the floor's definition and its
    curated-exempt allowlist live in exactly one place. An unstamped entry (no popularity block
    yet) is never a validation failure — that's what `npm run popularity:backfill` is for.
    Returns a list of human-readable error strings (empty when every entry clears)."""
    report = firmware_floor_audit.audit(data_dir)
    return [
        f"data/firmware/{e['id']}/firmware.md: below popularity floor "
        f"(stars={e['stars']} forks={e['forks']}, need stars>={firmware_floor_audit.STAR_FLOOR} "
        f"OR forks>={firmware_floor_audit.FORK_FLOOR})"
        for e in report["flagged"]
    ]


def main():
    total = errors = 0
    ids = known_ids()

    for kind, path in iter_data_files():
        total += 1
        rel = path.relative_to(REPO_ROOT)
        result = validate_file(path, kind=kind, ids=ids)
        if not result["ok"]:
            errors += 1
            for msg in result["errors"]:
                print(f"  ✗ {rel}: {msg}")

    for msg in check_orphan_firmware(ids):
        errors += 1
        print(f"  ✗ {msg}")

    for msg in check_popularity_floor():
        errors += 1
        print(f"  ✗ {msg}")

    print(f"\n{total - errors}/{total} valid, {errors} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
