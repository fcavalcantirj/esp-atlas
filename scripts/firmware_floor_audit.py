#!/usr/bin/env python3
"""Firmware popularity-floor AUDIT (SPEC-firmware-floor.md, "Prune the existing sub-floor entries").

The drain's popularity floor (jr/scorer.py STAR_FLOOR/DOWNLOAD_FLOOR, enforced in
jr/drain.py:score_candidates) gates NEW authoring only — it does not touch entries already in the
catalogue. This one-off audit is the other half: it scans every catalogued firmware
(data/firmware/*/firmware.md), resolves its GitHub repo from the `url:` field, fetches
stargazers_count, reads any launcher-download count stored in frontmatter (else unknown/0), and
flags firmware below BOTH floors (stars < STAR_FLOOR AND downloads < DOWNLOAD_FLOOR) as the prune
worklist.

Human-curated / known-good entries are EXEMPT (a maintainer chose them deliberately; popularity
doesn't override human curation). The firmware schema has no trust/tier field
(schema/firmware.schema.json is additionalProperties:false with no such key), so exemption falls
back to a hardcoded allowlist of the original curated set (CURATED_EXEMPT below).

    python3 scripts/firmware_floor_audit.py            # audit the real data/ dir (live: gh api)
    python3 scripts/firmware_floor_audit.py --data-dir /tmp/fixture

Maps to `npm run firmware:floor-audit`. Mirrors scripts/data_completion.py's structure. This is a
REPORT / worklist, never a gate — scripts/validate.py stays the deterministic CI gate; this never
affects its exit code. Network (gh api) is only hit on the real run; tests inject a fake
`fetch_stars`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
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


def default_fetch_stars(owner_repo: str) -> int | None:
    """stargazers_count for `owner_repo` via `gh api repos/<owner>/<repo>`. Returns None on any
    failure (missing gh, 404, network, malformed JSON) — the caller treats None as unknown/0. Only
    ever called on the real run; tests inject a fake."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{owner_repo}", "--jq", ".stargazers_count"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except (TypeError, ValueError):
        return None


def _firmware_downloads(fm: dict) -> int:
    """Launcher/M5Burner download count if the frontmatter happens to store one (the firmware
    schema doesn't model it today, so this is unknown/0 for the real dataset). Checks a few
    plausible key names defensively."""
    for key in ("download", "downloads", "m5burner_downloads"):
        val = fm.get(key)
        if isinstance(val, (int, float)):
            return int(val)
    return 0


def audit(data_dir=None, fetch_stars=default_fetch_stars, exempt=CURATED_EXEMPT):
    """Audit every catalogued firmware against the popularity floor. Returns:

        {
          "entries": [{"id", "url", "repo", "stars", "downloads", "exempt", "below_floor"}, ...],
          "flagged": [ ...the sub-floor, non-exempt entries (the prune worklist)... ],
          "exempt": [ ...ids skipped as human-curated... ],
        }

    `fetch_stars(owner_repo) -> int | None` is injectable (tests pass a no-network fake); None is
    treated as unknown → 0. An entry is flagged when it is NOT exempt AND stars < STAR_FLOOR AND
    downloads < DOWNLOAD_FLOOR.
    """
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    entries = []
    flagged = []
    exempt_ids = []
    for path in sorted(root.glob(DATA_PATTERNS["firmware"])):
        try:
            fm, _body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if not isinstance(fm, dict):
            continue
        fid = fm.get("id") or path.parent.name
        if fid in exempt:
            exempt_ids.append(fid)
            entries.append({"id": fid, "url": fm.get("url"), "repo": _owner_repo(fm.get("url")),
                            "stars": None, "downloads": None, "exempt": True, "below_floor": False})
            continue
        repo = _owner_repo(fm.get("url"))
        stars = fetch_stars(repo) if repo else None
        stars_val = stars or 0
        downloads = _firmware_downloads(fm)
        below = stars_val < STAR_FLOOR and downloads < DOWNLOAD_FLOOR
        entry = {"id": fid, "url": fm.get("url"), "repo": repo, "stars": stars,
                 "downloads": downloads, "exempt": False, "below_floor": below}
        entries.append(entry)
        if below:
            flagged.append(entry)
    flagged.sort(key=lambda e: ((e["stars"] or 0), e["downloads"], e["id"]))
    return {"entries": entries, "flagged": flagged, "exempt": exempt_ids}


def print_report(report):
    entries = report["entries"]
    flagged = report["flagged"]
    print("FIRMWARE POPULARITY-FLOOR AUDIT (prune worklist)")
    print(f"  floors: stars >= {STAR_FLOOR} OR downloads >= {DOWNLOAD_FLOOR}")
    print(f"  scanned {len(entries)} firmware · {len(report['exempt'])} curated-exempt · "
          f"{len(flagged)} below BOTH floors\n")
    print("SUB-FLOOR (prune candidates: id · stars · downloads):")
    if not flagged:
        print("    none — every non-curated firmware clears a floor")
    for e in flagged:
        stars = "unknown" if e["stars"] is None else e["stars"]
        print(f"    {e['id']}: stars={stars} downloads={e['downloads']}  ({e['repo']})")
    print(f"\nSUMMARY: {len(flagged)} of {len(entries)} catalogued firmware are below both floors "
          f"and not curated-exempt.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ root to scan (mainly for tests); defaults to <repo root>/data")
    parser.add_argument("--json", action="store_true", help="emit the raw audit dict as JSON")
    args = parser.parse_args(argv)

    report = audit(args.data_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
