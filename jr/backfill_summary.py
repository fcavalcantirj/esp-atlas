"""EspAtlas Jr — one-shot Groq summary/translation backfill (jr/backfill_summary.py).

Sweeps every `data/firmware/<id>/firmware.md`, fetches its repo's README, and calls
jr/groq_enrich.enrich_readme to write a grounded English `summary` (+ `readme_lang`, cited via
a `field: summary` sources[] entry) into the frontmatter, and a cached `readme.en.md` translation
alongside it whenever the README isn't already English. Both the README fetch and the Groq
client are injected — `default_fetch_readme`/`default_client` are the only network-touching
code here, never exercised under pytest (see jr/test_backfill_summary.py, which passes fakes).

Idempotent: a firmware whose frontmatter already carries a `summary` AND a `readme_sha` matching
the freshly fetched README is skipped without calling Groq again — a re-run only pays for
firmware whose README actually changed since it was last enriched. `--dry-run` reports intended
changes without writing anything (the README fetch still happens, to compute what WOULD change).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))

import yaml  # noqa: E402

from groq_enrich import default_client, enrich_readme  # noqa: E402
from summary_writer import readme_sha256, update_summary, write_readme_en  # noqa: E402

REPO = _JR_DIR.parent
FIRMWARE_DIR = REPO / "data" / "firmware"

_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s]+?)/?$")
_BRANCHES = ("main", "master")
_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")
_MAX_README_BYTES = 200_000


def repo_owner_and_name(url: str) -> tuple[str, str] | None:
    """A firmware record's `url:` -> (owner, repo), or None if it isn't a bare
    github.com/owner/repo link. Mirrors jr/backfill_popularity.py's own helper."""
    m = _GITHUB_URL_RE.match((url or "").strip())
    if not m:
        return None
    return m.group(1), re.sub(r"\.git$", "", m.group(2))


def default_fetch_readme(owner: str, repo: str) -> str | None:  # pragma: no cover — real network call
    """Real README fetch: raw.githubusercontent.com, `main` then `master`, the common README
    filenames — first hit wins. Mirrors jr/derive.py's own `default_raw` convention (small text
    files over urllib, a 404 is a fact, anything else raises). Returns None only when every
    branch/filename combination 404s or fails to connect."""
    import urllib.error
    import urllib.request

    for branch in _BRANCHES:
        for name in _README_NAMES:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
            req = urllib.request.Request(url, headers={"User-Agent": "esp-atlas-jr-backfill-summary/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.read(_MAX_README_BYTES).decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
            except urllib.error.URLError:
                continue
    return None


def _read_frontmatter(md_text: str) -> dict:
    if not md_text.startswith("---"):
        return {}
    _, front, _ = md_text.split("---", 2)
    return yaml.safe_load(front) or {}


def backfill(firmware_dir=None, *, fetch_readme=default_fetch_readme, client=default_client,
             today: str | None = None, dry_run: bool = False) -> dict:
    """Sweep every `<firmware_dir>/*/firmware.md` (default: the real data/firmware catalog),
    enriching it via Groq when its README is new or changed. `fetch_readme` and `client` are
    injectable so this runs fully offline in tests.

    Returns {"updated": [ids], "unchanged": [ids], "skipped": [(id, reason), ...]}. A skip
    (file always left untouched) covers: a `url:` that isn't a bare github.com/owner/repo link,
    a repo whose README can't be resolved on any tried branch/filename, or an enrichment call
    that returned no usable summary (empty/unusable README content, or an unparseable model
    response — see jr/groq_enrich.enrich_readme)."""
    root = Path(firmware_dir) if firmware_dir is not None else FIRMWARE_DIR
    today = today or dt.date.today().isoformat()

    updated, unchanged, skipped = [], [], []
    for path in sorted(root.glob("*/firmware.md")):
        fid = path.parent.name
        text = path.read_text(encoding="utf-8")
        fm = _read_frontmatter(text)
        owner_repo = repo_owner_and_name(fm.get("url"))
        if owner_repo is None:
            skipped.append((fid, "url is not a bare github.com/owner/repo link"))
            continue

        readme = fetch_readme(*owner_repo)
        if not readme:
            skipped.append((fid, "no resolvable README"))
            continue

        sha = readme_sha256(readme)
        if fm.get("summary") and fm.get("readme_sha") == sha:
            unchanged.append(fid)
            continue

        try:
            result = enrich_readme(readme, fm.get("name") or fid, client=client)
        except Exception as e:  # noqa: BLE001 — a rate-limit/transient must skip one, not abort the run (re-run is idempotent)
            skipped.append((fid, f"enrichment error: {type(e).__name__}: {str(e)[:80]}"))
            continue
        if not result.get("summary"):
            skipped.append((fid, "enrichment returned no usable summary"))
            continue

        rewrite = update_summary(
            text, summary=result["summary"], readme_lang=result.get("source_lang") or "en",
            readme_sha=sha, readme_url=fm.get("url"), today=today,
        )
        if not rewrite["changed"]:
            unchanged.append(fid)
            continue

        updated.append(fid)
        if not dry_run:
            path.write_text(rewrite["text"], encoding="utf-8")
            if result.get("readme_en"):
                write_readme_en(path.parent, result["readme_en"])

    return {"updated": updated, "unchanged": unchanged, "skipped": skipped}


def main(argv=None) -> int:  # pragma: no cover — exercised manually, never in CI/tests
    """CLI wiring over `backfill()` against the real catalog, the real README fetch, and the
    real Groq client. --dry-run reports what WOULD change without writing anything."""
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
