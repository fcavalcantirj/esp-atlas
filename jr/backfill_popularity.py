"""EspAtlas Jr — one-shot popularity backfill (jr/backfill_popularity.py).

The bug: jr/writers.py's `render_firmware` used to require BOTH stars and forks to be known
ints before writing ANY popularity block, so a repo whose forks_count genuinely wasn't known
at admission time (or was miscoerced downstream) lost its stars too. That's now fixed at the
writer, but the damage is already sitting on disk: as of 2026-09-20, 94 of 96 catalogued
firmware carry `popularity.stars` and only 42 also carry `popularity.forks`.

`update_popularity` is the pure rewrite: given a firmware.md's raw text and a live `gh api
repos/OWNER/REPO`-shaped payload, it returns the text with `popularity.{stars,forks,as_of}`
refreshed from the payload and a `sources[]` entry for `field: popularity` present (added only
if missing) — every other frontmatter field and the markdown body untouched, byte-identical.
IDEMPOTENT: re-running against an already-current record is a no-op (`changed: False`).

`api` is injected exactly as jr/forks.py's `default_api` — `api(owner, repo) -> raw GitHub repo
API shape` (mirrors `gh api repos/OWNER/REPO`'s real response shape); {} means unresolved (404,
deleted, or any gh failure). A repo GitHub redirects to a NEW full_name (renamed/moved) still
answers 200 — `backfill()` catches that identity drift explicitly and skips it too, rather than
silently re-pointing a record's stats at a repo it no longer names. Every function here down to
`backfill()`'s per-file loop is offline-testable with a fake api; `default_api` is the one real,
network-touching implementation, used only by a live run — and this module's own `main()` is NOT
run as part of this task; the real catalog sweep is a separate, explicitly-invoked step against
the pipeline's own GitHub token, with --dry-run available to preview it first.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))

REPO = _JR_DIR.parent
FIRMWARE_DIR = REPO / "data" / "firmware"

_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s]+?)/?$")


def default_api(owner: str, repo: str) -> dict:  # pragma: no cover — real network call, exercised manually
    """Real GitHub API client (`gh api repos/OWNER/REPO`, authed through `gh`), mirroring
    jr/forks.py's own `default_api`. Returns {} on any failure — 404, deleted, rate-limited,
    unparseable — so the caller's "unresolved" path is the same for every failure mode."""
    p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}"], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {}


def _split(md_text: str) -> tuple[dict, str]:
    """firmware.md text -> (frontmatter dict, body string INCLUDING its leading blank line(s)).
    Mirrors jr/catalog_migrate.py's own `_split` convention. `{}, md_text` for anything that
    isn't `---`-fenced YAML frontmatter (defensive; every real firmware.md is)."""
    if not md_text.startswith("---"):
        return {}, md_text
    _, front, body = md_text.split("---", 2)
    return (yaml.safe_load(front) or {}), body


def _render(fm: dict, body: str) -> str:
    """(frontmatter dict, body) -> firmware.md text, in the exact `author_firmware_record` shape
    (`---\\n<yaml>\\n---<body>`) so a no-op rewrite round-trips byte-identical."""
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{front}\n---{body}"


def repo_owner_and_name(url: str) -> tuple[str, str] | None:
    """A firmware record's `url:` -> (owner, repo), or None if it isn't a bare
    github.com/owner/repo link this module knows how to resolve."""
    m = _GITHUB_URL_RE.match((url or "").strip())
    if not m:
        return None
    return m.group(1), re.sub(r"\.git$", "", m.group(2))


def update_popularity(md_text: str, data: dict, today: str) -> dict:
    """Pure rewrite of one firmware.md's text from a live repo payload. `data` is the raw `gh
    api repos/OWNER/REPO` shape (or {} — unresolved: 404/deleted/any gh failure; a renamed repo
    is caught one level up, in `backfill()`, before this function ever sees it).

    Returns {"text": <md, rewritten or original>, "changed": bool, "reason": str|None}.
    `reason` is set (and `changed` is False, text is the untouched original) whenever nothing
    was written: "unresolved" (no usable stars/forks in `data`, including {}), or "up_to_date"
    (the computed popularity block already matches what's on disk — the idempotent no-op)."""
    fm, body = _split(md_text)
    stars = data.get("stargazers_count") if isinstance(data, dict) else None
    forks = data.get("forks_count") if isinstance(data, dict) else None
    new_pop = {}
    if isinstance(stars, int):
        new_pop["stars"] = stars
    if isinstance(forks, int):
        new_pop["forks"] = forks
    if not new_pop:
        return {"text": md_text, "changed": False, "reason": "unresolved"}
    new_pop["as_of"] = today

    sources = list(fm.get("sources") or [])
    url = fm.get("url")
    has_pop_source = any(isinstance(s, dict) and s.get("field") == "popularity" for s in sources)
    if fm.get("popularity") == new_pop and has_pop_source:
        return {"text": md_text, "changed": False, "reason": "up_to_date"}

    fm = dict(fm)
    fm["popularity"] = new_pop
    if not has_pop_source:
        sources = sources + [{"field": "popularity", "url": url, "verified": today}]
    fm["sources"] = sources
    return {"text": _render(fm, body), "changed": True, "reason": None}


def backfill(firmware_dir=None, api=default_api, today: str | None = None, dry_run: bool = False) -> dict:
    """Sweep every `<firmware_dir>/*/firmware.md` (default: the real data/firmware catalog),
    refreshing its popularity block from a live `gh api repos/OWNER/REPO`-shaped call. `api` and
    `today` are injectable so this runs fully offline in tests (mirrors
    scripts/popularity_backfill.py's own `backfill(..., fetch_repo_stats=..., today=...)`
    convention). `dry_run=True` computes and reports without writing anything.

    Returns {"updated": [ids], "unchanged": [ids], "skipped": [(id, reason), ...]}. A skip
    (file always left untouched) covers: a `url:` that isn't a bare github.com/owner/repo link,
    a repo `api` can't resolve (404 / deleted / any gh failure — signalled as {}), or a repo
    that answers under a DIFFERENT full_name than requested (gh api follows GitHub's rename
    redirect and still returns 200, so a renamed repo would otherwise silently re-point this
    record's stats at an identity it no longer names)."""
    import datetime as dt

    root = Path(firmware_dir) if firmware_dir is not None else FIRMWARE_DIR
    today = today or dt.date.today().isoformat()

    updated, unchanged, skipped = [], [], []
    for path in sorted(root.glob("*/firmware.md")):
        fid = path.parent.name
        text = path.read_text(encoding="utf-8")
        fm, _ = _split(text)
        owner_repo = repo_owner_and_name(fm.get("url"))
        if owner_repo is None:
            skipped.append((fid, "url is not a bare github.com/owner/repo link"))
            continue
        data = api(*owner_repo)
        if not data:
            skipped.append((fid, "repo unresolved (404 / deleted / gh failure)"))
            continue
        full_name = data.get("full_name") if isinstance(data, dict) else None
        if full_name and full_name.lower() != "/".join(owner_repo).lower():
            skipped.append((fid, f"repo renamed to {full_name}"))
            continue
        result = update_popularity(text, data, today)
        if not result["changed"]:
            if result["reason"] == "unresolved":
                skipped.append((fid, "no stars/forks in the API response"))
            else:
                unchanged.append(fid)
            continue
        updated.append(fid)
        if not dry_run:
            path.write_text(result["text"], encoding="utf-8")

    return {"updated": updated, "unchanged": unchanged, "skipped": skipped}


def main(argv=None) -> int:  # pragma: no cover — exercised manually, never in CI/tests
    """CLI wiring over `backfill()` against the real catalog and the real GitHub API. --dry-run
    reports what WOULD change without writing anything."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    args = parser.parse_args(argv)

    result = backfill(dry_run=args.dry_run)
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb}: {len(result['updated'])}")
    for fid in result["updated"]:
        print(f"  {fid}")
    print(f"already up to date: {len(result['unchanged'])}")
    print(f"skipped: {len(result['skipped'])}")
    for fid, reason in result["skipped"]:
        print(f"  {fid}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
