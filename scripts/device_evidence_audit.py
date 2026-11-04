#!/usr/bin/env python3
"""Device-build evidence AUDIT — read-only (review finding 3, 2026-11-04).

Jr's admission now requires a device-build signal before authoring a firmware record
(jr/device_evidence.py): an espressif32 platformio.ini, an ESP-IDF project (CMakeLists.txt
including project.cmake, or an idf_component.yml), an Arduino sketch (.ino) or a release .bin.
Records admitted BEFORE that gate never had to show one — rebelthor/warble, a Go server, got in on
its GitHub topics. This script runs the SAME check over every catalogued firmware's GitHub repo and
lists the ones with none, for the owner to review. It decides nothing and writes nothing: no data,
no ledger, no recipe is touched.

LIVE: one check costs 1–8 `gh api` / raw.githubusercontent.com reads (jr/device_evidence.MAX_CALLS).

    python3 scripts/device_evidence_audit.py               # every firmware in data/firmware
    python3 scripts/device_evidence_audit.py --only warble,bruce
    python3 scripts/device_evidence_audit.py --json

Three outcomes per firmware: a signal (its kind + citing URL), NO signal (the review list), or
UNKNOWN (an endpoint failed for a reason other than 404 — re-run later). A firmware whose url is
not a github.com repo cannot be checked this way and is listed as such. Always exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (REPO_ROOT / "apps" / "core" / "src", REPO_ROOT / "jr"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import device_evidence  # noqa: E402
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402
from firmware_floor_audit import _owner_repo  # noqa: E402


def audit(data_dir=None, check=device_evidence.check, only: set[str] | None = None) -> dict:
    """{"entries", "no_signal", "unknown", "not_github"} over every catalogued firmware (or the
    ids in `only`). `check(owner_repo) -> device_evidence result` is injectable for tests."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    entries, no_signal, unknown, not_github = [], [], [], []
    for path in sorted(root.glob(DATA_PATTERNS["firmware"])):
        try:
            fm, _body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if not isinstance(fm, dict):
            continue
        fid = fm.get("id") or path.parent.name
        if only and fid not in only:
            continue
        entry = {"id": fid, "url": fm.get("url"), "repo": _owner_repo(fm.get("url")),
                 "ok": None, "kind": None, "evidence": None, "notes": []}
        entries.append(entry)
        if not entry["repo"]:
            not_github.append(entry)
            continue
        res = check(entry["repo"])
        entry.update(ok=res.get("ok"), kind=res.get("kind"), evidence=res.get("url"), notes=res.get("notes") or [])
        if entry["ok"] is False:
            no_signal.append(entry)
        elif entry["ok"] is None:
            unknown.append(entry)
    return {"entries": entries, "no_signal": no_signal, "unknown": unknown, "not_github": not_github}


def print_report(report: dict) -> None:
    entries = report["entries"]
    print("FIRMWARE DEVICE-BUILD EVIDENCE AUDIT (live, read-only)")
    print("  signal: espressif32 platformio.ini · ESP-IDF project · Arduino .ino · release .bin")
    print(f"  scanned {len(entries)} firmware · {len(report['no_signal'])} with NO signal · "
          f"{len(report['unknown'])} unknown · {len(report['not_github'])} not a GitHub repo\n")
    print("NO DEVICE-BUILD SIGNAL (owner review: id · repo):")
    for e in report["no_signal"] or []:
        print(f"    {e['id']}  ({e['repo']})")
    if not report["no_signal"]:
        print("    none")
    print("\nUNKNOWN (an endpoint failed; re-run):")
    for e in report["unknown"]:
        print(f"    {e['id']}  ({e['repo']}): {'; '.join(e['notes'])[:160]}")
    if not report["unknown"]:
        print("    none")
    print("\nNOT A GITHUB REPO (not checkable here):")
    for e in report["not_github"]:
        print(f"    {e['id']}  ({e['url']})")
    if not report["not_github"]:
        print("    none")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None, help="override the data/ root (tests)")
    parser.add_argument("--only", default=None, help="comma-separated firmware ids to check")
    parser.add_argument("--json", action="store_true", help="emit the raw audit dict as JSON")
    args = parser.parse_args(argv)
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only else None
    report = audit(args.data_dir, only=only)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
