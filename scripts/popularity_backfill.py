#!/usr/bin/env python3
"""One-off popularity BACKFILL (SPEC-firmware-floor.md, "Backfill").

Stamps a dated `popularity` snapshot onto every existing data/firmware/*/firmware.md that does
NOT already carry one, so the offline CI floor gate (scripts/firmware_floor_audit.py --ci) has
data for today's catalog. For each unstamped firmware it:

  1. fetches LIVE GitHub stars + forks via `gh api repos/<owner>/<repo>` and checks identity,
  2. writes only verified counts with a GitHub-specific date and field citations.

Unresolved or renamed repos are skipped; a missing API value is never converted to zero.

Downloads are NOT fetched or stamped — the popularity floor is stars-or-forks only.

Never overwrites an existing popularity block (idempotent — re-running only touches the still
-unstamped remainder). The live fetch sits behind an injectable function so tests run fully
offline; the real network is only hit on an actual run.

    python3 scripts/popularity_backfill.py            # real run: live gh api
    python3 scripts/popularity_backfill.py --data-dir /tmp/fixture

Maps to `npm run popularity:backfill`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402


def _owner_repo(url: str) -> str | None:
    """owner/repo from a bare github.com project URL, or None otherwise."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "github.com" or \
            parsed.query or parsed.fragment:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return f"{parts[0]}/{parts[1].removesuffix('.git')}".lower()


def default_fetch_repo_stats(owner_repo: str) -> dict | None:
    """Identity and counts from `gh api repos/<owner>/<repo>`; None on a failed fetch.
    Only called on a real run; tests inject a fake."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{owner_repo}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        d = json.loads(out.stdout)
        if not isinstance(d, dict):
            return None
        return {"full_name": d.get("full_name"), "stars": d.get("stargazers_count"),
                "forks": d.get("forks_count")}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _stamp(path: Path, fm: dict, body: str, stars: int | None, forks: int | None, today: str) -> None:
    """Rewrite `path` with a popularity block (before sources) + a `popularity` source citation.
    Preserves every other field in author-order."""
    sources = fm.pop("sources", []) or []
    pop = {}
    if type(stars) is int and stars >= 0:
        pop["stars"] = stars
    if type(forks) is int and forks >= 0:
        pop["forks"] = forks
    pop["github_as_of"] = today
    pop["as_of"] = today
    fm["popularity"] = pop
    sources = list(sources)
    sources.append({"field": "popularity", "url": fm.get("url"), "verified": today})
    for field in ("popularity.github_as_of", "popularity.stars", "popularity.forks"):
        if field == "popularity.github_as_of" or field.rsplit(".", 1)[1] in pop:
            sources.append({"field": field, "url": fm.get("url"), "verified": today})
    fm["sources"] = sources
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n", encoding="utf-8")


def backfill(data_dir=None, fetch_repo_stats=default_fetch_repo_stats, today: str | None = None):
    """Stamp popularity onto every unstamped firmware under `data_dir`. Returns
    {"stamped": [...], "skipped": [...]} (each a list of firmware ids). Never overwrites an
    existing popularity block. `fetch_repo_stats` is injectable so tests run offline."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    today = today or dt.date.today().isoformat()
    stamped, skipped = [], []
    for path in sorted(root.glob(DATA_PATTERNS["firmware"])):
        try:
            fm, body = parse_frontmatter(path)
        except (ValueError, OSError):
            continue
        if not isinstance(fm, dict):
            continue
        fid = fm.get("id") or path.parent.name
        if isinstance(fm.get("popularity"), dict):
            skipped.append(fid)                     # already stamped — never overwrite
            continue
        repo = _owner_repo(fm.get("url"))
        stats = fetch_repo_stats(repo) if repo else None
        full_name = stats.get("full_name") if isinstance(stats, dict) else None
        if not isinstance(full_name, str) or full_name.lower() != repo:
            skipped.append(fid)
            continue
        stars = stats.get("stars")
        forks = stats.get("forks")
        if (type(stars) is not int or stars < 0) and (type(forks) is not int or forks < 0):
            skipped.append(fid)
            continue
        _stamp(path, fm, body, stars, forks, today)
        stamped.append(fid)
    return {"stamped": stamped, "skipped": skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="override the data/ root (mainly for tests); defaults to <repo root>/data")
    args = parser.parse_args(argv)

    result = backfill(args.data_dir)
    print("POPULARITY BACKFILL")
    print(f"  stamped {len(result['stamped'])} · skipped {len(result['skipped'])} "
          f"(already stamped)")
    for fid in result["stamped"]:
        print(f"  + {fid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
