#!/usr/bin/env python3
"""G2 destructive-operation guard (scripts/g2_guard.py, SPEC-firmware-boards.md §4).

A deleted firmware record that is curated-exempt, floor-passing, or ≥1000 stars fails the
PR unless `jr/overrides/<id>.json` is in the same change (the explicit, logged override —
a human saying "yes, delete this on purpose"). A deleted recipe fails unless its firmware
is also deleted under an override. Everything else (below-floor, unstamped, unlisted
records) stays deletable: G2 protects high-signal rows, not every row.

Offline and deterministic: the deleted record is read from the BASE ref (`git show
<base>:<path>`), so the check judges what was actually removed, not what remains. The
floor comes from apps/core/src/esp_atlas_core/floor.py (imported, never re-typed) and the
curated-exempt list from scripts/firmware_floor_audit.py (imported, never re-typed).

Usage in CI (a dedicated `g2-guard` job with fetch-depth: 0):
    python3 scripts/g2_guard.py                      # base origin/main (or $GITHUB_BASE_REF)

Locally:
    python3 scripts/g2_guard.py --base <sha-or-ref>  # e.g. origin/main, a tag, a commit

Exit 0 when every deletion is guarded or harmless; exit 1 with ::error:: lines otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import yaml  # noqa: E402
from esp_atlas_core.floor import clears_popularity_floor  # noqa: E402
from firmware_floor_audit import CURATED_EXEMPT  # noqa: E402

# A firmware with this many stored stars is high-signal no matter what the floors say
# (today every stars>=1000 record also clears the floor; this clause survives floor edits).
G2_STAR_GUARD = 1000

FIRMWARE_PREFIX = "data/firmware/"
FIRMWARE_SUFFIX = "/firmware.md"
RECIPE_PREFIX = "data/recipes/"
RECIPE_SUFFIX = "/recipe.md"
OVERRIDE_PREFIX = "jr/overrides/"


def firmware_id_of(path: str) -> str | None:
    """<id> from data/firmware/<id>/firmware.md, else None."""
    if path.startswith(FIRMWARE_PREFIX) and path.endswith(FIRMWARE_SUFFIX):
        rest = path[len(FIRMWARE_PREFIX):-len(FIRMWARE_SUFFIX)]
        return rest or None
    return None


def recipe_firmware_id(path: str) -> str | None:
    """The firmware id from data/recipes/<board>__<firmware>/recipe.md, else None."""
    if path.startswith(RECIPE_PREFIX) and path.endswith(RECIPE_SUFFIX):
        dirname = path[len(RECIPE_PREFIX):-len(RECIPE_SUFFIX)]
        if "__" in dirname:
            _board, fid = dirname.split("__", 1)
            return fid or None
    return None


def deleted_paths(diff_text: str) -> list[str]:
    """Paths with status D from `git diff --name-status --no-renames` output."""
    out = []
    for line in diff_text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == "D":
            out.append(parts[1])
    return out


def protection_reasons(fid: str, fm: dict) -> list[str]:
    """Why deleting this firmware record is refused (empty when deletable). Judged from the
    record as it was BEFORE deletion: curated-exempt, floor-passing stored popularity, or
    ≥1000 stored stars. Unstamped records (no popularity block) clear nothing and pass."""
    reasons = []
    if fid in CURATED_EXEMPT:
        reasons.append("curated-exempt")
    pop = fm.get("popularity") if isinstance(fm, dict) else None
    pop = pop if isinstance(pop, dict) else {}
    stars, forks = pop.get("stars") or 0, pop.get("forks") or 0
    if clears_popularity_floor(pop.get("stars"), pop.get("forks")):
        reasons.append(f"floor-passing (stars={stars} forks={forks})")
    if (pop.get("stars") or 0) >= G2_STAR_GUARD:
        reasons.append(f"stars>={G2_STAR_GUARD}")
    return reasons


def check(deleted: list[str], show_file, head_has) -> list[str]:
    """The pure gate: `deleted` repo-relative paths; `show_file(base, path)` returns the base
    file text or None; `head_has(path)` says whether the path exists in HEAD. Returns error
    lines (empty when the change is guarded or harmless).

    A recipe deletion rides along with its firmware's deletion: it passes when the firmware
    is deleted in the same change AND that firmware deletion itself passes this gate (below
    floor with no override, or guarded by an override). A recipe deleted while its firmware
    stays always fails — that is the two-step orphaning move (strip the evidence, then take
    the firmware as "unused")."""
    errors = []
    firmware_removed_cleanly = set()
    for path in deleted:
        fid = firmware_id_of(path)
        if fid is None:
            continue
        text = show_file(path)
        if text is None:
            continue
        try:
            fm = yaml.safe_load(text.split("---")[1])
        except (yaml.YAMLError, IndexError):
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        reasons = protection_reasons(fid, fm)
        if not reasons:
            firmware_removed_cleanly.add(fid)
            continue
        if head_has(f"{OVERRIDE_PREFIX}{fid}.json"):
            firmware_removed_cleanly.add(fid)
            continue
        errors.append(f"::error file={path}::G2 guard: deleting firmware '{fid}' "
                      f"({', '.join(reasons)}) without jr/overrides/{fid}.json in this change")
    for path in deleted:
        fid = recipe_firmware_id(path)
        if fid is None:
            continue
        if fid in firmware_removed_cleanly:
            continue
        errors.append(f"::error file={path}::G2 guard: deleting recipe '{path}' whose firmware "
                      f"'{fid}' is not deleted under an override in this change")
    return errors


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None,
                    help="base ref for the diff (default: origin/$GITHUB_BASE_REF, else origin/main)")
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    diff = _git("diff", "--name-status", "--no-renames", f"{base}...HEAD", cwd=args.repo)
    if diff.returncode != 0:
        print(f"::error::G2 guard: cannot diff {base}...HEAD: {(diff.stderr or '').strip()[:200]}")
        return 1

    def show_file(path: str) -> str | None:
        p = _git("show", f"{base}:{path}", cwd=args.repo)
        return p.stdout if p.returncode == 0 else None

    def head_has(path: str) -> bool:
        return _git("show", f"HEAD:{path}", cwd=args.repo).returncode == 0

    errors = check(deleted_paths(diff.stdout), show_file, head_has)
    for line in errors:
        print(line)
    if errors:
        print(f"G2 GUARD FAILED: {len(errors)} unguarded deletion(s)", file=sys.stderr)
        return 1
    print("G2 guard green: no unguarded deletions of high-signal firmware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
