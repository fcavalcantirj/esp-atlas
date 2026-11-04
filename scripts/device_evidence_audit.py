#!/usr/bin/env python3
"""Device-build evidence AUDIT — read-only (review finding 3, 2026-11-04).

Jr's admission requires evidence that a repo TARGETS an ESP chip before authoring a firmware record
(jr/device_evidence.py): an espressif32 platformio.ini, an ESP-IDF project stating its target, an
Arduino sketch naming an ESP board, or a release .bin that jr/esp_image.py validates as a whole
ESP image. Records admitted BEFORE that gate never had to show one — rebelthor/warble, a Go
server, got in on its GitHub topics. This script runs the SAME check over every catalogued firmware's GitHub repo and
sorts it into the gate's three classes, for the owner to review. It decides nothing and writes
nothing: no data, no ledger, no recipe is touched.

LIVE: one check costs 1–15 `gh api` / raw.githubusercontent.com / ranged release-asset reads
(jr/device_evidence.MAX_CALLS).

    python3 scripts/device_evidence_audit.py               # every firmware in data/firmware
    python3 scripts/device_evidence_audit.py --only warble,bruce
    python3 scripts/device_evidence_audit.py --json

Classes: ESP_TARGET (the evidence kind + citing URL), NOT_DEVICE_FIRMWARE (no build signal at
all), NEEDS_REVIEW (only an ambiguous signal: the citing URL and why). Plus UNKNOWN (an endpoint
failed for a reason other than 404 — re-run later) and NOT A GITHUB REPO (cannot be checked this
way). Always exits 0.
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


CLASSES = (device_evidence.ESP_TARGET, device_evidence.NOT_DEVICE_FIRMWARE, device_evidence.NEEDS_REVIEW)


def audit(data_dir=None, check=device_evidence.check, only: set[str] | None = None) -> dict:
    """{"entries", "esp_target", "not_device_firmware", "needs_review", "unknown", "not_github"}
    over every catalogued firmware (or the ids in `only`). `check(owner_repo) -> device_evidence
    result` is injectable for tests."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    report: dict = {"entries": [], **{c: [] for c in CLASSES}, "unknown": [], "not_github": []}
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
                 "ok": None, "verdict": None, "kind": None, "evidence": None, "why": None, "notes": []}
        report["entries"].append(entry)
        if not entry["repo"]:
            report["not_github"].append(entry)
            continue
        res = check(entry["repo"])
        entry.update(ok=res.get("ok"), verdict=res.get("verdict"), kind=res.get("kind"), evidence=res.get("url"),
                     notes=res.get("notes") or [])
        if entry["verdict"] == device_evidence.NEEDS_REVIEW:
            entry["why"] = device_evidence.review_note(res)["why"]
        report[entry["verdict"] if entry["verdict"] in CLASSES else "unknown"].append(entry)
    return report


def _section(title: str, entries: list[dict], line) -> None:
    print(f"\n{title}:")
    for e in entries:
        print("    " + line(e))
    if not entries:
        print("    none")


def print_report(report: dict) -> None:
    print("FIRMWARE DEVICE-BUILD EVIDENCE AUDIT (live, read-only)")
    print("  esp_target: espressif32 platformio.ini · ESP-IDF project + stated target · "
          "Arduino sketch + ESP board · release .bin validated as an ESP image")
    print(f"  scanned {len(report['entries'])} firmware · "
          + " · ".join(f"{len(report[c])} {c}" for c in CLASSES)
          + f" · {len(report['unknown'])} unknown · {len(report['not_github'])} not a GitHub repo")
    _section("ESP TARGET (id · repo: evidence)", report[device_evidence.ESP_TARGET],
             lambda e: f"{e['id']}  ({e['repo']}): {e['kind']} {e['evidence']}")
    _section("NOT DEVICE FIRMWARE (no build signal; owner review: id · repo)", report[device_evidence.NOT_DEVICE_FIRMWARE],
             lambda e: f"{e['id']}  ({e['repo']})")
    _section("NEEDS REVIEW (no ESP target stated; owner review: id · repo: citation — why)", report[device_evidence.NEEDS_REVIEW],
             lambda e: f"{e['id']}  ({e['repo']}): {e['kind']} {e['evidence']} — {e['why']}")
    _section("UNKNOWN (an endpoint failed; re-run)", report["unknown"],
             lambda e: f"{e['id']}  ({e['repo']}): {'; '.join(e['notes'])[:160]}")
    _section("NOT A GITHUB REPO (not checkable here)", report["not_github"], lambda e: f"{e['id']}  ({e['url']})")


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
