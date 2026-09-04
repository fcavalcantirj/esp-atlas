"""EspAtlas Jr — catalog migration/sweep functions (jr/catalog_migrate.py).

Pure, tested functions over a firmware.md's raw text (YAML frontmatter + markdown body) that
will (eventually, via `main()`) sweep `data/firmware/*/firmware.md` to:

  1. `strip_downloads` — remove any leftover `downloads:` line from the popularity block
     (SPEC-firmware-floor.md: downloads are dead going forward, never a stored metric).
  2. `resolve_entry_fork` — rewrite an entry whose repo is itself a GitHub fork to point at its
     canonical SOURCE instead (jr/forks.py), so the catalog cites the real, more-popular origin.
  3. `below_floor` — flag an entry that no longer clears the popularity floor (e.g. after a
     `resolve_entry_fork` rewrite pulls in the source's own, possibly lower, stars/forks).

NONE of this runs at import time or in CI/tests — `main()` is guarded behind
`if __name__ == "__main__":` and is the ONLY thing in this module that touches
`data/firmware` on disk. Every function above it is a pure string/dict transform, tested
offline with real catalog-style markdown fixtures and an injected `api` (no network — see
jr/forks.py's own module docstring for the `api` contract).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import yaml

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
from forks import default_api, resolve_source  # noqa: E402
from scorer import FORK_FLOOR, STAR_FLOOR  # noqa: E402

REPO = _JR_DIR.parent
FIRMWARE_DIR = REPO / "data" / "firmware"

_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s]+?)/?$")


def _split(md_text: str) -> tuple[dict, str]:
    """firmware.md text -> (frontmatter dict, body string INCLUDING its leading blank line(s)).
    Mirrors jr/tools.py's `_frontmatter` parsing convention. `{}, md_text` for anything that
    isn't `---`-fenced YAML frontmatter (defensive; every real firmware.md is)."""
    if not md_text.startswith("---"):
        return {}, md_text
    _, front, body = md_text.split("---", 2)
    return (yaml.safe_load(front) or {}), body


def _render(fm: dict, body: str) -> str:
    """(frontmatter dict, body) -> firmware.md text, in the exact `author_firmware_record`
    shape (`---\\n<yaml>\\n---<body>`) so a no-op rewrite round-trips byte-identical."""
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{front}\n---{body}"


def strip_downloads(md_text: str) -> str:
    """Remove `popularity.downloads`, if present. IDEMPOTENT: text with no `downloads` key
    (including the output of a prior call) round-trips unchanged. `stars`/`forks`/`as_of` are
    never touched."""
    fm, body = _split(md_text)
    pop = fm.get("popularity")
    if not isinstance(pop, dict) or "downloads" not in pop:
        return md_text
    pop = dict(pop)
    pop.pop("downloads")
    fm = dict(fm)
    fm["popularity"] = pop
    return _render(fm, body)


def below_floor(stars: int | None, forks: int | None) -> bool:
    """SPEC-firmware-floor.md: True iff BOTH stars < STAR_FLOOR AND forks < FORK_FLOOR — reuses
    jr/scorer.py's own floor constants (never re-derived) so a catalog sweep and the live drain
    can never disagree on where the line is."""
    return (stars or 0) < STAR_FLOOR and (forks or 0) < FORK_FLOOR


def resolve_entry_fork(md_text: str, api) -> dict:
    """If the entry's `url:` repo is a GitHub fork, rewrite `md_text` to point at its canonical
    SOURCE (url, maintainer, popularity.stars/forks, every `sources[]` url citing the old repo)
    via jr/forks.resolve_source. A non-fork entry (or one whose `url:` isn't a bare
    github.com/owner/repo link) is returned unchanged.

    Returns {"text": <md, rewritten or original>, "changed": bool, "source_full_name": str|None,
    "already_present": bool}. `already_present` mirrors `changed` — a rewrite only ever happens
    because the fork's canonical identity is a DIFFERENT, already-existing repo (the fork isn't
    a new thing; its source is), which is exactly the dedupe signal a caller (`main()`, or a
    human reviewing the sweep) needs: this source may already be catalogued under another id."""
    fm, body = _split(md_text)
    url = (fm.get("url") or "").strip()
    m = _GITHUB_URL_RE.match(url)
    if not m:
        return {"text": md_text, "changed": False, "source_full_name": None, "already_present": False}
    owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
    original_full = f"{owner}/{repo}".lower()

    source = resolve_source(owner, repo, api) or {}
    source_full = source.get("full_name")
    if not source_full or source_full.lower() == original_full:
        return {"text": md_text, "changed": False, "source_full_name": source_full, "already_present": False}

    old_url = f"https://github.com/{owner}/{repo}"
    new_url = f"https://github.com/{source_full}"

    fm = dict(fm)
    fm["url"] = new_url
    fm["maintainer"] = source_full.split("/")[0]
    pop = fm.get("popularity")
    if isinstance(pop, dict):
        pop = dict(pop)
        if "stars" in source:
            pop["stars"] = source["stars"]
        if "forks" in source:
            pop["forks"] = source["forks"]
        fm["popularity"] = pop
    sources = fm.get("sources")
    if isinstance(sources, list):
        fm["sources"] = [
            {**s, "url": new_url} if isinstance(s, dict) and (s.get("url") or "").startswith(old_url) else s
            for s in sources
        ]

    return {"text": _render(fm, body), "changed": True,
            "source_full_name": source_full, "already_present": True}


def main() -> None:  # pragma: no cover — exercised manually, never in CI/tests
    """Apply strip_downloads + resolve_entry_fork + below_floor across every real
    data/firmware/*/firmware.md, reporting what it WOULD change. Deliberately not wired to
    write anything back here — that's a separate, explicitly-run migration step (mirrors
    scripts/strip_downloads.py's own one-off-migration shape), never a side effect of importing
    this module."""
    api = default_api
    changed_downloads, changed_forks, sub_floor = [], [], []
    for path in sorted(FIRMWARE_DIR.glob("*/firmware.md")):
        text = path.read_text()
        fid = path.parent.name

        stripped = strip_downloads(text)
        if stripped != text:
            changed_downloads.append(fid)
            text = stripped

        fork_result = resolve_entry_fork(text, api)
        if fork_result["changed"]:
            changed_forks.append((fid, fork_result["source_full_name"]))
            text = fork_result["text"]

        fm, _ = _split(text)
        pop = fm.get("popularity") or {}
        if below_floor(pop.get("stars"), pop.get("forks")):
            sub_floor.append(fid)

    print(f"downloads-stripped: {len(changed_downloads)}")
    print(f"fork-rewritten: {len(changed_forks)}")
    for fid, source_full in changed_forks:
        print(f"  {fid} -> {source_full}")
    print(f"below-floor after sweep: {len(sub_floor)}")
    for fid in sub_floor:
        print(f"  {fid}")


if __name__ == "__main__":
    main()
