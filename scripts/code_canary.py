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
    queued = gh("pr", "list", "--repo", repo_slug, "--state", "open", "--label", PASS_LABEL,
                "--json", "number", "--limit", "50")
    try:
        rows, waiting = json.loads(out or "[]"), json.loads(queued or "[]")
    except json.JSONDecodeError as e:
        raise Unreadable(f"merged list unparsable: {e}") from e
    # an open PR labelled agent-pass is a merge already requested (--auto waits for its checks): it counts
    # against the cap like a merged one (review BLOCK of #1809, 2026-11-19)
    return ([f"#{r.get('number')}" for r in rows if str(r.get("mergedAt", "")) >= since]
            + [f"#{r.get('number')} (queued)" for r in waiting])


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


def verdict_from_comments(gh, repo_slug: str, pr: int) -> tuple[str, str | None]:
    """(current head, newest verdict JSON for that head or None) from the PR's marker comments — the one
    source of truth both review lanes write (jr/agent_review.py, docs/REVIEW-CONTRACT.md "Who runs it")."""
    sys.path.insert(0, str(REPO / "jr"))
    import agent_review
    try:
        head = json.loads(gh("pr", "view", str(pr), "--repo", repo_slug, "--json", "headRefOid") or "{}")["headRefOid"]
        comments = json.loads(gh("api", f"repos/{repo_slug}/issues/{pr}/comments", "--paginate") or "[]")
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise Unreadable(f"PR head or comments unreadable: {e}") from e
    v = agent_review.verdict_for_head(comments, head)
    return head.lower(), (json.dumps({k: v[k] for k in ("verdict", "head", "findings", "checked")}) if v else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--head", help="the exact head (default: the PR's current head when --from-comments)")
    ap.add_argument("--author", default="")
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--from-comments", action="store_true",
                    help="read the newest marker verdict comment for the PR's current head instead of VERDICT_JSON")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        head, verdict_json = a.head, os.environ.get("VERDICT_JSON")
        if a.from_comments:
            head, verdict_json = verdict_from_comments(demand_canary.default_gh, a.repo_slug, a.pr)
            if verdict_json is None:
                print(f"code canary: no verdict comment for #{a.pr} at its current head {head[:8]}; nothing to do")
                print("outcome: no_verdict")
                return 0
        if not head:
            print("code canary: --head is required without --from-comments", file=sys.stderr)
            return 2
        outcome = decide(pr=a.pr, head=head, verdict_json=verdict_json, repo_slug=a.repo_slug,
                         now=datetime.now(timezone.utc), env=dict(os.environ), dry_run=a.dry_run,
                         autonomy_path=demand_canary.AUTONOMY, gh=demand_canary.default_gh)
    except Unreadable as e:
        print(f"code canary: cannot act: {e}", file=sys.stderr)
        return 2
    print(f"outcome: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
