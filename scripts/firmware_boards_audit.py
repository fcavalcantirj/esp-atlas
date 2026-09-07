#!/usr/bin/env python3
"""G1 audit — does every firmware map every board its own repo declares? (SPEC-firmware-boards §4)

Reads the signals Jr persisted next to each firmware record (`data/firmware/<id>/signals.json`,
written by jr/stage_boardmap.py from the repo's release assets, platformio.ini, CI matrix and
IDF targets, each resolved to a catalogued board) and compares the resolved boards with the
recipes that exist (`data/recipes/<board>__<id>/`). Offline: nothing is fetched here.

    python3 scripts/firmware_boards_audit.py            # report
    python3 scripts/firmware_boards_audit.py --ci       # GitHub-Actions warnings, exit 0 (warn mode)
    python3 scripts/firmware_boards_audit.py --ci --strict   # exit 1 when any firmware is under-mapped

Warn mode is the plan's first setting: it becomes blocking (`--strict` in the workflow) once the
known under-maps are closed by Track B runs. A firmware with no signals.json is "unmeasured",
never a failure: the audit only judges what Jr has actually read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def audit(data_dir: Path) -> dict:
    """{"measured": [{id, resolved, recipes, missing, extra, fetched}], "unmeasured": [ids]}"""
    measured, unmeasured = [], []
    recipes_dir = data_dir / "recipes"
    for fmd in sorted((data_dir / "firmware").glob("*/firmware.md")):
        fid = fmd.parent.name
        sig = fmd.parent / "signals.json"
        if not sig.exists():
            unmeasured.append(fid)
            continue
        try:
            doc = json.loads(sig.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            unmeasured.append(fid)
            continue
        if not doc.get("signals") and doc.get("errors"):
            unmeasured.append(fid)          # a read that hit unavailable endpoints and saw nothing is not a measurement
            continue
        resolved = sorted(set((doc.get("resolved") or {}).get("boards") or []))
        recipes = sorted(p.name[: -(len(fid) + 2)] for p in recipes_dir.glob(f"*__{fid}") if p.is_dir())
        measured.append({
            "id": fid, "fetched": doc.get("fetched"), "resolved": resolved, "recipes": recipes,
            "missing": sorted(set(resolved) - set(recipes)),      # declared by the repo, no recipe yet
            "extra": sorted(set(recipes) - set(resolved)),        # recipe without a build signal (human/launcher)
            "unresolved": len((doc.get("resolved") or {}).get("unresolved") or []),
        })
    return {"measured": measured, "unmeasured": unmeasured}


def render(report: dict, ci: bool = False) -> list[str]:
    lines = []
    under = [m for m in report["measured"] if m["missing"]]
    for m in report["measured"]:
        tag = "UNDER-MAPPED" if m["missing"] else "ok"
        lines.append(f"{m['id']}: {len(m['recipes'])} recipe(s), {len(m['resolved'])} board(s) declared "
                     f"(signals {m['fetched']}), missing {len(m['missing'])}, extra {len(m['extra'])}, "
                     f"unresolved tokens {m['unresolved']} — {tag}")
        if m["missing"]:
            lines.append(f"   missing: {', '.join(m['missing'])}")
            if ci:
                lines.append(f"::warning file=data/firmware/{m['id']}/firmware.md::G1 under-mapped: "
                             f"{len(m['missing'])} declared board(s) without a recipe: {', '.join(m['missing'])}")
    lines.append(f"SUMMARY: {len(report['measured'])} measured, {len(under)} under-mapped, "
                 f"{sum(len(m['missing']) for m in under)} missing recipe(s), {len(report['unmeasured'])} unmeasured (no signals.json)")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=REPO / "data")
    ap.add_argument("--ci", action="store_true", help="emit GitHub Actions ::warning:: lines")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any measured firmware is under-mapped")
    args = ap.parse_args(argv)
    report = audit(args.data_dir)
    for line in render(report, ci=args.ci):
        print(line)
    if args.strict and any(m["missing"] for m in report["measured"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
