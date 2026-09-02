#!/usr/bin/env python3
"""Firmware popularity-floor AUDIT + CI GATE (SPEC-firmware-floor.md).

Reads the STORED, dated `popularity` block (stars/downloads/as_of) from every catalogued
firmware's frontmatter — NO live fetch, fully offline and deterministic — and flags any firmware
below BOTH floors (stars < STAR_FLOOR AND downloads < DOWNLOAD_FLOOR) that isn't curated-exempt.
That stored data is written at author time by the drain (jr/tools.author_firmware_and_recipes)
and backfilled onto pre-existing entries by scripts/popularity_backfill.py.

An entry with NO popularity block yet is reported separately as "unstamped" — it just needs
backfilling, it is NOT a floor failure (a fresh catalog must not hard-fail CI before the backfill
runs).

Human-curated / known-good entries are EXEMPT (a maintainer chose them deliberately; popularity
doesn't override human curation). The firmware schema carries no trust/tier field, so exemption
falls back to a hardcoded allowlist of the original curated set (CURATED_EXEMPT below).

    python3 scripts/firmware_floor_audit.py            # audit the real data/ dir (offline)
    python3 scripts/firmware_floor_audit.py --data-dir /tmp/fixture
    python3 scripts/firmware_floor_audit.py --ci       # exit non-zero if any below-both-floors

Maps to `npm run firmware:floor-audit`. With `--ci` this is the deterministic CI gate wired into
.github/workflows/validate.yml: it EXITS NON-ZERO when any firmware is below both floors (unstamped
entries are ignored for the exit code). Without `--ci` it is a report only and always exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402

# Mirrors jr/scorer.py's STAR_FLOOR / DOWNLOAD_FLOOR (kept in sync by hand: jr/ is a standalone
# package with its own venv and is not importable from the repo-root scripts runtime).
STAR_FLOOR = 25
DOWNLOAD_FLOOR = 500

# Human-curated / known-good firmware — exempt from the floor regardless of popularity. Used
# because the firmware schema carries no trust/tier field; this is the original curated set.
CURATED_EXEMPT = frozenset({
    "bruce", "esp32marauder", "rogueduck", "evil-m5project", "m5stick-nemo", "meshtastic",
    "esphome", "tasmota", "wled", "openmqttgateway", "launcher", "nerdminer-v2", "usbarmyknife",
    "m5-crystal", "infiltra", "cathack", "esp32-bit-pirate", "xiaozhi-esp32",
})


def _owner_repo(url: str) -> str | None:
    """owner/repo from a github.com project url, or None if it isn't a resolvable github repo."""
    u = (url or "").strip()
    if "github.com/" not in u:
        return None
    tail = u.split("github.com/", 1)[1].strip("/")
    parts = [p for p in tail.split("/") if p]
    if len(parts) < 2:
        return None
    repo = parts[1].removesuffix(".git")
    return f"{parts[0]}/{repo}".lower()


def _popularity(fm: dict) -> dict | None:
    """The stored popularity snapshot ({stars, downloads, as_of}) if this firmware has one, else
    None (unstamped). Never fetches — reads only what author/backfill persisted."""
    pop = fm.get("popularity")
    return pop if isinstance(pop, dict) else None


def audit(data_dir=None, exempt=CURATED_EXEMPT):
    """Audit every catalogued firmware against the popularity floor, OFFLINE, from stored data.
    Returns:

        {
          "entries":   [{"id", "url", "repo", "stars", "downloads", "as_of",
                         "exempt", "stamped", "below_floor"}, ...],
          "flagged":   [ ...sub-floor, non-exempt, STAMPED entries (the CI-failing set)... ],
          "unstamped": [ ...entries with no popularity block yet (need backfilling)... ],
          "exempt":    [ ...ids skipped as human-curated... ],
        }

    An entry is `flagged` when it is NOT exempt, IS stamped, AND stars < STAR_FLOOR AND
    downloads < DOWNLOAD_FLOOR. Unstamped entries are reported separately and never flagged.
    """
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    entries, flagged, unstamped, exempt_ids = [], [], [], []
    for path in sorted(root.glob(DATA_PATTERNS["firmware"])):
        try:
            fm, _body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if not isinstance(fm, dict):
            continue
        fid = fm.get("id") or path.parent.name
        repo = _owner_repo(fm.get("url"))
        pop = _popularity(fm)
        entry = {"id": fid, "url": fm.get("url"), "repo": repo,
                 "stars": (pop or {}).get("stars"), "downloads": (pop or {}).get("downloads"),
                 "as_of": (pop or {}).get("as_of"),
                 "exempt": fid in exempt, "stamped": pop is not None, "below_floor": False}
        entries.append(entry)
        if entry["exempt"]:
            exempt_ids.append(fid)
            continue
        if pop is None:
            unstamped.append(entry)
            continue
        stars = pop.get("stars") or 0
        downloads = pop.get("downloads") or 0
        entry["below_floor"] = stars < STAR_FLOOR and downloads < DOWNLOAD_FLOOR
        if entry["below_floor"]:
            flagged.append(entry)
    flagged.sort(key=lambda e: ((e["stars"] or 0), (e["downloads"] or 0), e["id"]))
    unstamped.sort(key=lambda e: e["id"])
    return {"entries": entries, "flagged": flagged, "unstamped": unstamped, "exempt": exempt_ids}


def print_report(report):
    entries = report["entries"]
    flagged = report["flagged"]
    unstamped = report["unstamped"]
    print("FIRMWARE POPULARITY-FLOOR AUDIT (stored, offline)")
    print(f"  floors: stars >= {STAR_FLOOR} OR downloads >= {DOWNLOAD_FLOOR}")
    print(f"  scanned {len(entries)} firmware · {len(report['exempt'])} curated-exempt · "
          f"{len(flagged)} below BOTH floors · {len(unstamped)} unstamped\n")
    print("SUB-FLOOR (below BOTH floors — CI FAILS on these: id · stars · downloads):")
    if not flagged:
        print("    none — every stamped, non-curated firmware clears a floor")
    for e in flagged:
        print(f"    {e['id']}: stars={e['stars']} downloads={e['downloads']} "
              f"as_of={e['as_of']}  ({e['repo']})")
    print("\nUNSTAMPED (no popularity block yet — run popularity:backfill; NOT a CI failure):")
    if not unstamped:
        print("    none — every non-curated firmware carries a popularity snapshot")
    for e in unstamped:
        print(f"    {e['id']}  ({e['repo']})")
    print(f"\nSUMMARY: {len(flagged)} below-both-floors, {len(unstamped)} unstamped, of "
          f"{len(entries)} catalogued firmware.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ root to scan (mainly for tests); defaults to <repo root>/data")
    parser.add_argument("--json", action="store_true", help="emit the raw audit dict as JSON")
    parser.add_argument("--ci", action="store_true",
                        help="CI gate: exit non-zero if any firmware is below BOTH floors "
                             "(unstamped entries are ignored for the exit code)")
    args = parser.parse_args(argv)

    report = audit(args.data_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    if args.ci and report["flagged"]:
        print(f"\nCI GATE FAILED: {len(report['flagged'])} firmware below both popularity floors "
              f"(stars < {STAR_FLOOR} AND downloads < {DOWNLOAD_FLOOR}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
