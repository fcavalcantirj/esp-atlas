#!/usr/bin/env python3
"""PR guard for added firmware — the catalog's admission rules, re-checked LIVE in CI
(scripts/jr_pr_guard.py). For every `data/firmware/<id>/firmware.md` ADDED by the PR:

  - `url` is a github.com/owner/repo; the repository answers (200), is not a fork, not archived;
  - the live stars/forks clear the floor (esp_atlas_core.floor — one definition), and the
    record's dated `popularity` snapshot is present (the offline floor gate reads it);
  - `socs` is non-empty.

Whoever authored the record — EspAtlas Jr, a human, a submission — the gate is the same, so
"trust the gate" means something. Uses $GITHUB_TOKEN when present (Actions provides one);
anonymous otherwise (60 calls/h, a PR adds a handful of records).

    python3 scripts/jr_pr_guard.py                     # base origin/$GITHUB_BASE_REF or origin/main
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "core" / "src"))
from esp_atlas_core.floor import clears_popularity_floor  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
_GH = re.compile(r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def frontmatter(text: str) -> dict:
    import yaml
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def default_fetch(owner_repo: str) -> dict:
    """{status, json} for GET /repos/<owner_repo>."""
    req = urllib.request.Request(f"https://api.github.com/repos/{owner_repo}",
                                 headers={"User-Agent": "esp-atlas-jr-pr-guard/0.1", "Accept": "application/vnd.github+json",
                                          **({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return {"status": r.status, "json": json.loads(r.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "json": {}}


def check_record(path: str, fm: dict, fetch=default_fetch) -> list[str]:
    """Pure given `fetch`: the violations for one added firmware record."""
    out = []
    m = _GH.match(str(fm.get("url") or ""))
    if not m:
        return [f"{path}: url is not a github.com/owner/repo ({fm.get('url')!r})"]
    owner_repo = f"{m.group(1)}/{m.group(2)}"
    if not fm.get("socs"):
        out.append(f"{path}: socs is empty")
    pop = fm.get("popularity")
    if not (isinstance(pop, dict) and isinstance(pop.get("stars"), int) and isinstance(pop.get("forks"), int) and pop.get("as_of")):
        out.append(f"{path}: no dated popularity snapshot (stars, forks, as_of) — the offline floor gate cannot read it")
    r = fetch(owner_repo)
    if r.get("status") != 200:
        out.append(f"{path}: {owner_repo} does not answer on GitHub (HTTP {r.get('status')})")
        return out
    doc = r.get("json") or {}
    if doc.get("fork"):
        out.append(f"{path}: {owner_repo} is a fork of {(doc.get('parent') or {}).get('full_name') or '?'}")
    if doc.get("archived"):
        out.append(f"{path}: {owner_repo} is archived")
    stars, forks = doc.get("stargazers_count"), doc.get("forks_count")
    if not clears_popularity_floor(stars, forks):
        out.append(f"{path}: {owner_repo} is below the floor live ({stars} stars / {forks} forks)")
    return out


def added_firmware(diff_text: str) -> list[str]:
    out = []
    for line in diff_text.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] == "A" and re.match(r"^data/firmware/[^/]+/firmware\.md$", parts[1]):
            out.append(parts[1])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None)
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    diff = subprocess.run(["git", "diff", "--name-status", "--no-renames", f"{base}...HEAD"], cwd=args.repo,
                          capture_output=True, text=True, timeout=60)
    if diff.returncode != 0:
        print(f"::error::git diff against {base} failed: {diff.stderr.strip()[:200]}")
        return 1
    added = added_firmware(diff.stdout)
    problems = []
    for rel in added:
        fm = frontmatter((args.repo / rel).read_text(encoding="utf-8"))
        problems += check_record(rel, fm)
    for m in problems:
        print(f"::error::{m}")
    print(f"PR guard: {len(added)} added firmware record(s), {'green' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
