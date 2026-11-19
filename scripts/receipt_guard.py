#!/usr/bin/env python3
"""Is this tick PR mergeable on its evidence receipts alone? (scripts/receipt_guard.py)

SPEC-jr-review-routing.md §7, phase 2. A tick PR routed `jr-review` adds firmware and recipes; every
recipe Jr writes carries the independent evidence check's receipt in its notes ("Evidence check v3 PASS
— named: the source names m5cardputer-adv"). A person used to read those PRs; 27 a week, hours each.
This guard reads them instead:

  E1  every recipe the PR ADDS carries a `PASS` receipt (UNCERTAIN or none: a person or the agent reviewer);
  E2  every such receipt holds AGAIN when the checker (jr/autoreview.check, the same rules) is re-run here
      on the live upstream: the firmware repo's description, README, root platformio.ini and release
      asset names — a stale or misstated receipt cannot merge;
  E3  the PR edits no existing catalog record (a modified data/**/*.md is a content change the checker
      does not cover) and deletes nothing under data/;
  E4  it adds at least one recipe (a PR with nothing receipted has nothing this guard can vouch for).

Bookkeeping (ledger, signals, snapshots) is free. Exit 0: eligible (every receipt printed). Exit 1: not
eligible, the rule named. Exit 2: not a `jr/tick-*` branch, or git / upstream unreadable (an unreadable
upstream is never a verdict: the PR simply waits for a person).

    python3 scripts/receipt_guard.py                       # branch and base from the Actions env
    python3 scripts/receipt_guard.py --base origin/main --head HEAD --branch jr/tick-20261117-1900
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "jr"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import autoreview  # noqa: E402
import board_alias  # noqa: E402
from esp_atlas_core.frontmatter import parse_frontmatter_text  # noqa: E402

BRANCH_PREFIX = "jr/tick-"
_RECEIPT = re.compile(r"Evidence check v(\d+) (PASS|UNCERTAIN|FAIL)")
_RECIPE = re.compile(r"^data/recipes/([^/]+)/recipe\.md$")
_OWNER_REPO = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+)")
USER_AGENT = "esp-atlas-receipt-guard/1.0 (+https://github.com/fcavalcantirj/esp-atlas)"
TIMEOUT = 15.0


class Unreadable(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise Unreadable(f"git {' '.join(args[:3])}: {e}") from e
    if p.returncode != 0:
        raise Unreadable(f"git {' '.join(args[:3])}: {p.stderr.strip()[:200]}")
    return p.stdout


def default_api(path: str):
    """GET api.github.com/<path> as JSON (the token when Actions provides one)."""
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Unreadable(f"GitHub API {path}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise Unreadable(f"GitHub API {path}: {type(e).__name__}") from e


def default_raw(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Unreadable(f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise Unreadable(f"{url}: {type(e).__name__}") from e


def live_sources(owner_repo: str, api=default_api, raw=default_raw) -> dict:
    """The checker's sources for one firmware repo, read now: description, README, root platformio.ini,
    release asset names. A missing file is an empty source; an unreadable endpoint raises Unreadable."""
    meta = api(f"repos/{owner_repo}") or {}
    readme_doc = api(f"repos/{owner_repo}/readme") or {}
    readme = base64.b64decode(readme_doc.get("content") or "").decode("utf-8", "ignore") if isinstance(readme_doc, dict) else ""
    branch = meta.get("default_branch") or "HEAD"
    pio = raw(f"https://raw.githubusercontent.com/{owner_repo}/{branch}/platformio.ini") or ""
    rels = api(f"repos/{owner_repo}/releases?per_page=10") or []
    assets = [a.get("name", "") for rel in (rels if isinstance(rels, list) else []) if isinstance(rel, dict)
              for a in rel.get("assets") or [] if isinstance(a, dict)]
    return {"description": meta.get("description") or "", "readme": readme, "platformio": pio,
            "assets": " ".join(dict.fromkeys(assets))}


def receipt_of(frontmatter: dict) -> tuple[str, str] | None:
    """(rules version, verdict) from the recipe notes, or None when it carries no receipt."""
    notes = frontmatter.get("notes")
    text = "\n".join(notes) if isinstance(notes, list) else str(notes or "")
    m = _RECEIPT.search(text)
    return (m.group(1), m.group(2)) if m else None


def check(repo: Path, *, base: str, head: str, branch: str, api=default_api, raw=default_raw,
          catalog: dict | None = None) -> tuple[list[str], list[str]]:
    """(problems, receipt lines). Raises Unreadable when git, the catalog or an upstream cannot be read."""
    if not (branch or "").startswith(BRANCH_PREFIX):
        raise Unreadable(f"{branch!r} is not a {BRANCH_PREFIX}* branch")
    catalog = catalog if catalog is not None else board_alias.atlas_boards(repo)
    problems, lines = [], [f"tick PR on {branch}: {base}...{head}"]
    changes = [(ln.split("\t")[0][0], ln.split("\t")[-1]) for ln in _git(repo, "diff", "--name-status", "--no-renames", f"{base}...{head}").split("\n") if ln.strip()]
    added_recipes = [p for s, p in changes if s == "A" and _RECIPE.match(p)]
    edited = sorted(p for s, p in changes if s == "M" and p.startswith("data/") and p.endswith(".md"))
    deleted = sorted(p for s, p in changes if s == "D" and p.startswith("data/"))
    if edited:
        problems.append(f"E3 existing record(s) edited: {', '.join(edited[:5])}")
    if deleted:
        problems.append(f"E3 data deleted: {', '.join(deleted[:5])}")
    if not added_recipes:
        problems.append("E4 no recipe added: nothing receipted to vouch for")
    checked: dict[str, dict] = {}
    for path in added_recipes:
        fm, _ = parse_frontmatter_text(_git(repo, "show", f"{head}:{path}"))
        rec = receipt_of(fm)
        board, fw = fm.get("board"), fm.get("firmware")
        if rec is None:
            problems.append(f"E1 {path}: no evidence receipt")
            continue
        version, verdict = rec
        if verdict != autoreview.PASS:
            problems.append(f"E1 {path}: receipt v{version} {verdict}, not PASS")
            continue
        try:
            fw_fm, _ = parse_frontmatter_text(_git(repo, "show", f"{head}:data/firmware/{fw}/firmware.md"))
        except Unreadable:
            problems.append(f"E2 {path}: firmware record data/firmware/{fw}/firmware.md not at {head}")
            continue
        m = _OWNER_REPO.match(str(fw_fm.get("url") or ""))
        if not m:
            problems.append(f"E2 {path}: firmware url is not a github.com repository")
            continue
        owner_repo = f"{m.group(1)}/{m.group(2)}"
        if owner_repo not in checked:
            checked[owner_repo] = live_sources(owner_repo, api=api, raw=raw)
        v = autoreview.check(board, checked[owner_repo], catalog)
        why = (v.reasons or [""])[0]
        if v.verdict != autoreview.PASS:
            problems.append(f"E2 {path}: receipt v{version} PASS, but the live re-check is {v.verdict} (rules v{v.rules_version}): {why}")
            continue
        lines.append(f"E1/E2 {path}: receipt v{version} PASS; live re-check v{v.rules_version} PASS — {why}")
    lines.append("E3 no existing record edited, nothing deleted" if not (edited or deleted) else "E3 see above")
    return problems, lines


def default_base() -> str:
    ref = os.environ.get("GITHUB_BASE_REF")
    return f"origin/{ref}" if ref else "origin/main"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--branch", default=None)
    ap.add_argument("--report-only", action="store_true",
                    help="print the verdict and exit 0 whatever it is (the CI job: the tick canary recomputes it)")
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    try:
        branch = a.branch or os.environ.get("GITHUB_HEAD_REF") or _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        problems, lines = check(repo, base=a.base or default_base(), head=a.head, branch=branch)
    except Unreadable as e:
        print(f"receipt guard: cannot read: {e}", file=sys.stderr)
        return 0 if a.report_only else 2
    for ln in lines:
        print(f"  {ln}")
    if problems:
        print("\nNOT ELIGIBLE on receipts alone:")
        for p in problems:
            print(f"  ✗ {p}")
        return 0 if a.report_only else 1
    print("\n✓ receipt guard: every added recipe carries a PASS receipt that holds on the live upstream")
    return 0


if __name__ == "__main__":
    sys.exit(main())
