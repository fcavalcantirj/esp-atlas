#!/usr/bin/env python3
"""One-off popularity BACKFILL (SPEC-firmware-floor.md, "Backfill").

Stamps a dated `popularity` snapshot onto every existing data/firmware/*/firmware.md that does
NOT already carry one, so the offline CI floor gate (scripts/firmware_floor_audit.py --ci) has
data for today's catalog. For each unstamped firmware it:

  1. fetches LIVE GitHub stars via `gh api repos/<owner>/<repo>` (graceful on 404/missing gh),
  2. matches the launcher / M5Burner catalog (mirrors jr.tools.fetch_launcher_catalog) by repo or
     name to recover a download count (0 if unmatched),
  3. writes popularity{stars, downloads, as_of=today} + a per-field `popularity` source citation.

Never overwrites an existing popularity block (idempotent — re-running only touches the still
-unstamped remainder). Both live fetches sit behind injectable functions so tests run fully
offline; the real network is only hit on an actual run.

    python3 scripts/popularity_backfill.py            # real run: live gh api + launcher catalog
    python3 scripts/popularity_backfill.py --data-dir /tmp/fixture

Maps to `npm run popularity:backfill`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402

# Mirrors jr/tools.py's launcher endpoint (jr/ isn't importable from the scripts runtime — its
# own venv — so the one API call is reissued here rather than importing jr.tools directly).
LAUNCHERHUB = "https://api.launcherhub.net/giveMeTheList"


def _owner_repo(url: str) -> str | None:
    """owner/repo (lowercased) from a github.com project url, or None if not a github repo."""
    u = (url or "").strip()
    if "github.com/" not in u:
        return None
    tail = u.split("github.com/", 1)[1].strip("/")
    parts = [p for p in tail.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1].removesuffix('.git')}".lower()


def default_fetch_stars(owner_repo: str) -> int | None:
    """stargazers_count for `owner_repo` via `gh api repos/<owner>/<repo>`. Returns None on any
    failure (missing gh, 404, network, malformed output) — the caller treats None as 0. Only ever
    called on the real run; tests inject a fake."""
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


def default_fetch_catalog() -> list[dict]:
    """The launcher/M5Burner community catalog (mirrors jr.tools.fetch_launcher_catalog — one
    call). Only ever called on the real run; tests inject a fake."""
    req = urllib.request.Request(LAUNCHERHUB, headers={"User-Agent": "esp-atlas-jr/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data if isinstance(data, list) else data.get("data", [])


def _catalog_downloads(catalog: list[dict], owner_repo: str | None, name: str | None) -> int:
    """Match a firmware to the launcher catalog by github repo (owner/repo) first, then by exact
    (case-insensitive) name, and return its `download` count. 0 when unmatched."""
    name_l = (name or "").strip().lower()
    for e in catalog or []:
        gh = _owner_repo(e.get("github") or "")
        if owner_repo and gh and gh == owner_repo:
            return int(e.get("download") or 0)
    for e in catalog or []:
        if name_l and (e.get("name") or "").strip().lower() == name_l:
            return int(e.get("download") or 0)
    return 0


def _stamp(path: Path, fm: dict, body: str, stars: int, downloads: int, today: str) -> None:
    """Rewrite `path` with a popularity block (before sources) + a `popularity` source citation.
    Preserves every other field in author-order."""
    sources = fm.pop("sources", []) or []
    fm["popularity"] = {"stars": int(stars), "downloads": int(downloads), "as_of": today}
    sources = list(sources)
    sources.append({"field": "popularity", "url": fm.get("url"), "verified": today})
    fm["sources"] = sources
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    path.write_text(f"---\n{front}\n---\n\n{body.strip()}\n", encoding="utf-8")


def backfill(data_dir=None, fetch_stars=default_fetch_stars, fetch_catalog=default_fetch_catalog,
             today: str | None = None):
    """Stamp popularity onto every unstamped firmware under `data_dir`. Returns
    {"stamped": [...], "skipped": [...]} (each a list of firmware ids). Never overwrites an
    existing popularity block. The launcher catalog is fetched at most once (lazily, only if
    there's at least one unstamped firmware). `fetch_stars` / `fetch_catalog` are injectable so
    tests run offline."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    today = today or dt.date.today().isoformat()
    catalog = None
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
        if catalog is None:
            catalog = fetch_catalog() or []
        repo = _owner_repo(fm.get("url"))
        stars = fetch_stars(repo) if repo else None
        downloads = _catalog_downloads(catalog, repo, fm.get("name"))
        _stamp(path, fm, body, stars or 0, downloads, today)
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
