#!/usr/bin/env python3
"""One-off DOWNLOADS-STRIP migration (SPEC-firmware-floor.md).

The popularity floor no longer consults downloads at all (stars-or-forks only) and downloads are
no longer a stored metric. This migration removes the now-stale `downloads:` line from every
`data/firmware/*/firmware.md`'s `popularity:` block (keeping `stars`/`forks`/`as_of`), and drops
any `sources` entry that cited ONLY `downloads` (a `field: downloads` citation with nothing else
backed by it).

IDEMPOTENT: an entry that no longer carries a `downloads` line (and no `downloads`-only source)
is left byte-for-byte untouched and reported as "skipped" — a second run is a no-op.

    python3 scripts/strip_downloads.py            # migrate the real data/ dir
    python3 scripts/strip_downloads.py --data-dir /tmp/fixture
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402


def _strip_downloads_field(fm: dict) -> bool:
    """Remove `popularity.downloads` if present. Returns True if it changed anything."""
    pop = fm.get("popularity")
    if isinstance(pop, dict) and "downloads" in pop:
        pop.pop("downloads")
        return True
    return False


def _strip_downloads_only_source(fm: dict) -> bool:
    """Remove any `sources` entry whose `field` is literally `downloads`. Returns True if it
    changed anything."""
    sources = fm.get("sources")
    if not isinstance(sources, list):
        return False
    kept = [s for s in sources if not (isinstance(s, dict) and s.get("field") == "downloads")]
    if len(kept) == len(sources):
        return False
    fm["sources"] = kept
    return True


def strip_downloads(data_dir=None) -> dict:
    """Migrate every firmware.md under `data_dir` (default: the real data/ root). Returns
    {"stripped": [...ids actually rewritten...], "skipped": [...ids already clean, untouched...]}."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    stripped, skipped = [], []
    for path in sorted(root.glob(DATA_PATTERNS["firmware"])):
        try:
            fm, body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if not isinstance(fm, dict):
            continue
        fid = fm.get("id") or path.parent.name
        changed_field = _strip_downloads_field(fm)
        changed_source = _strip_downloads_only_source(fm)
        if not (changed_field or changed_source):
            skipped.append(fid)               # already clean — never rewritten
            continue
        front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
        path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n", encoding="utf-8")
        stripped.append(fid)
    return {"stripped": stripped, "skipped": skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ root (mainly for tests); defaults to <repo root>/data")
    args = parser.parse_args(argv)

    result = strip_downloads(args.data_dir)
    print("DOWNLOADS-STRIP MIGRATION")
    print(f"  stripped {len(result['stripped'])} · skipped {len(result['skipped'])} (already clean)")
    for fid in result["stripped"]:
        print(f"  - {fid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
