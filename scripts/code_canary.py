#!/usr/bin/env python3
"""The code canary: a code PR the agent reviewer PASSed at this exact head merges itself
(scripts/code_canary.py; docs/REVIEW-CONTRACT.md; .github/workflows/agent-review.yml).

  C1  `jr/autonomy.json` has `code_automerge: true` (a reviewed PR turns it on);
  C2  the repository variable JR_CODE_AUTOMERGE is not "0" (the kill switch);
  C3  the verdict JSON (VERDICT_JSON, the reviewer's structured output) is readable, says PASS and names
      THIS head — a verdict for another sha is no verdict;
  C4  at most one agent-merged PR per hour (label `agent-pass` is put on the PR before the merge request and
      counted over the last 60 minutes);
  C5  then `gh pr merge --merge --auto --match-head-commit <head>`: lands only when every required check is
      green at exactly this head. A BLOCK verdict labels the PR `needs-human` (the reviewer already posted
      the findings) and merges nothing.

Every decision is printed; exit 0 always except an unreadable input (2); `--dry-run` never acts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import demand_canary  # noqa: E402

FLAG, VARIABLE = "code_automerge", "JR_CODE_AUTOMERGE"
PASS_LABEL, HUMAN_LABEL = "agent-pass", "needs-human"
HOURLY_CAP = 1
Unreadable = demand_canary.Unreadable


def read_verdict(text: str | None) -> dict:
    try:
        doc = json.loads(text or "")
    except json.JSONDecodeError as e:
        raise Unreadable(f"verdict JSON unreadable: {e}") from e
    if not isinstance(doc, dict) or doc.get("verdict") not in ("PASS", "BLOCK"):
        raise Unreadable("verdict JSON has no PASS/BLOCK verdict")
    return doc


def merged_last_hour(gh, repo_slug: str, now: datetime) -> list[str]:
    since = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = gh("pr", "list", "--repo", repo_slug, "--state", "merged", "--label", PASS_LABEL,
             "--search", f"merged:>={since}", "--json", "number,mergedAt", "--limit", "50")
    try:
        rows = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        raise Unreadable(f"merged list unparsable: {e}") from e
    return [f"#{r.get('number')}" for r in rows if str(r.get("mergedAt", "")) >= since]


def decide(*, pr: int, head: str, verdict_json: str | None, repo_slug: str, now: datetime, env: dict,
           autonomy_path: Path = demand_canary.AUTONOMY, gh=demand_canary.default_gh, dry_run: bool = False,
           out=None) -> str:
    out = out or sys.stdout
    say = lambda s: print(s, file=out)  # noqa: E731
    on, why = demand_canary.switches(autonomy_path, env, flag=FLAG, variable=VARIABLE)
    say(why.replace("D1", "C1").replace("D2", "C2"))
    if not on:
        return "off"
    v = read_verdict(verdict_json)
    if str(v.get("head", "")).lower() != head.lower():
        say(f"C3 the verdict names head {v.get('head')!r}, not {head}: no verdict for this head")
        return "stale_verdict"
    if v["verdict"] == "BLOCK":
        say(f"C3 BLOCK at {head}: {len(v.get('findings') or [])} finding(s); label {HUMAN_LABEL}, no merge")
        if not dry_run:
            gh("pr", "edit", str(pr), "--repo", repo_slug, "--add-label", HUMAN_LABEL)
        return "block"
    say(f"C3 PASS at exact head {head}; checked: {', '.join(v.get('checked') or [])[:200]}")
    done = merged_last_hour(gh, repo_slug, now)
    if len(done) >= HOURLY_CAP:
        say(f"C4 hourly cap: {', '.join(done)} merged in the last hour; this one waits for the next run")
        return "capped"
    say("C4 hourly cap free")
    if dry_run:
        say(f"C5 dry run: would label {PASS_LABEL} and request merge --auto --match-head-commit {head}")
        return "dry_run"
    gh("pr", "edit", str(pr), "--repo", repo_slug, "--add-label", PASS_LABEL)
    gh("pr", "merge", str(pr), "--repo", repo_slug, "--merge", "--auto", "--match-head-commit", head)
    say(f"C5 #{pr} labelled {PASS_LABEL}; merge requested at exact head {head}")
    return "merge_requested"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--author", default="")
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        outcome = decide(pr=a.pr, head=a.head, verdict_json=os.environ.get("VERDICT_JSON"), repo_slug=a.repo_slug,
                         now=datetime.now(timezone.utc), env=dict(os.environ), dry_run=a.dry_run)
    except Unreadable as e:
        print(f"code canary: cannot act: {e}", file=sys.stderr)
        return 2
    print(f"outcome: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
