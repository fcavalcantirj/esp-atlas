#!/usr/bin/env python3
"""main's head always gets a validate run (scripts/validate_main.py; last step of every canary job).

GitHub starts no workflow for a push made with a workflow's own GITHUB_TOKEN, so a PR the machine merges
leaves main's new head without CI (2026-11-19: #1799, merge commit 9ba8d76f, zero runs). The CI watcher reads
the newest validate run on main and never saw such a commit. The documented exception is workflow_dispatch:
this script asks whether main's head has a validate run in any state and, when it has none, starts one on
main. It runs after every canary decision (`if: always()`), so a merge that landed later through a queued
auto-merge is picked up by the next canary run.

Never fails its job: GitHub trouble prints `unavailable` and exits 0. `--dry-run` starts nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

WORKFLOW = "validate.yml"


def default_gh(*args: str) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {p.stderr.strip()[:300]}")
    return p.stdout


def ensure(gh, slug: str, dry_run: bool = False) -> str:
    """has_run | dispatched | would_dispatch | unavailable: <why>. Dispatches only on a readable, empty run list."""
    try:
        head = json.loads(gh("api", f"repos/{slug}/commits/main") or "{}").get("sha")
        if not head:
            return "unavailable: main's head is unreadable"
        doc = json.loads(gh("api", f"repos/{slug}/actions/workflows/{WORKFLOW}/runs?head_sha={head}&per_page=5") or "null")
        runs = doc.get("workflow_runs") if isinstance(doc, dict) else None
        if not isinstance(runs, list):
            return "unavailable: the run list is unreadable"
        if runs:
            print(f"validate-main: main {head[:8]} has {len(runs)} validate run(s) ({runs[0].get('status')})")
            return "has_run"
        if dry_run:
            print(f"validate-main: main {head[:8]} has no validate run; a real run would start one")
            return "would_dispatch"
        gh("workflow", "run", WORKFLOW, "--repo", slug, "--ref", "main")
        print(f"validate-main: main {head[:8]} had no validate run; started one (workflow_dispatch)")
        return "dispatched"
    except Exception as e:  # noqa: BLE001 — this step must never turn a canary job red
        return f"unavailable: {str(e)[:200]}"


def main(argv=None, gh=default_gh) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    print(f"outcome: {ensure(gh, a.repo_slug, a.dry_run)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
