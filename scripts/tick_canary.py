#!/usr/bin/env python3
"""The tick canary: a review-routed tick PR whose every added recipe holds its PASS receipt merges itself
(scripts/tick_canary.py). SPEC-jr-review-routing.md §7, phase 2: fully passing review PRs at their exact
head, with a kill switch and a daily cap (one a day at first; four since 2026-11-21, see DAILY_CAP).

  T1  `jr/autonomy.json` has `tick_automerge: true` (a reviewed PR turns it on);
  T2  the repository variable JR_TICK_AUTOMERGE is not "0" (the instant kill switch);
  T3  the branch is `jr/tick-*` and the PR carries the `jr-review` label (an AUTO-routed tick PR merges
      itself already; this canary is for the ones that used to wait for a person);
  T4  fewer than DAILY_CAP `jr-review` tick PRs merged today (UTC);
  T5  scripts/receipt_guard.py says the PR is eligible on its receipts alone: every added recipe carries a
      PASS receipt that holds on the live upstream, no existing record edited, nothing deleted;
  T6  then `gh pr merge --merge --auto --match-head-commit <head>`: the merge lands only when every
      required check is green at EXACTLY this head.

Every decision is printed. Exit 0 always except an unreadable input (2). `--dry-run` never acts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import demand_canary  # noqa: E402
import receipt_guard  # noqa: E402

FLAG, VARIABLE = "tick_automerge", "JR_TICK_AUTOMERGE"
BRANCH_PREFIX, LABEL = "jr/tick-", "jr-review"
# One a day at first (2026-11-17). 2026-11-21: Jr opened 10 review-routed tick PRs over Nov 18-20 (about 3.3 a
# day) and one merged a day, so the queue only grew and the tick, which never re-proposes what an open PR
# holds, yielded nothing for 24 ticks. The first three canary merges (#1835, #1836, #1860) were audited
# against their upstreams and are correct. Four a day drains the queue; every merge still needs every added
# recipe's receipt to hold on the live upstream, and JR_TICK_AUTOMERGE=0 stops it.
DAILY_CAP = 4
TICK_SCOPE = ("data/", "jr/proposed_ledger.json", "jr/board_cooldown.json", "docs/telemetry/")
Unreadable = demand_canary.Unreadable


def pr_labels(gh, repo_slug: str, pr: int) -> list[str]:
    out = gh("pr", "view", str(pr), "--repo", repo_slug, "--json", "labels")
    try:
        return sorted(str(l.get("name", "")) for l in json.loads(out or "{}").get("labels") or [])
    except (json.JSONDecodeError, AttributeError) as e:
        raise Unreadable(f"labels unparsable: {e}") from e


def decide(*, pr: int, head: str, branch: str, base: str, repo_slug: str, today: str, env: dict,
           autonomy_path: Path = demand_canary.AUTONOMY, gh=demand_canary.default_gh, api=None, raw=None,
           repo: Path = REPO, dry_run: bool = False, out=None, paths=None) -> str:
    out = out or sys.stdout
    say = lambda s: print(s, file=out)  # noqa: E731
    on, why = demand_canary.switches(autonomy_path, env, flag=FLAG, variable=VARIABLE)
    say(why.replace("D1", "T1").replace("D2", "T2"))
    if not on:
        return "off"
    if not (branch or "").startswith(BRANCH_PREFIX):
        say(f"T3 {branch!r} is not a {BRANCH_PREFIX}* branch")
        return "not_tick"
    labels = pr_labels(gh, repo_slug, pr)
    if LABEL not in labels:
        say(f"T3 #{pr} carries no {LABEL} label (an AUTO-routed tick PR merges itself): nothing to do")
        return "not_review"
    say(f"T3 review-routed tick PR #{pr} on {branch} at {head}")
    bad = demand_canary.out_of_scope(demand_canary.changed_paths(base, head, repo) if paths is None else paths, TICK_SCOPE)
    if bad is None or bad:
        say("T3 scope: " + ("changed paths unreadable" if bad is None else
                            f"changes outside {', '.join(TICK_SCOPE)}: {', '.join(bad[:5])}") + " — never merged by a canary")
        return "out_of_scope"
    done = demand_canary.merged_today(gh, repo_slug, today, prefix=BRANCH_PREFIX, label=LABEL)
    if len(done) >= DAILY_CAP:
        say(f"T4 daily cap: {len(done)} review-routed tick PR(s) merged today ({', '.join(done)}); this one waits")
        return "capped"
    say(f"T4 daily cap free ({len(done)} merged today)")
    kw = {k: v for k, v in (("api", api), ("raw", raw)) if v is not None}
    try:
        problems, lines = receipt_guard.check(repo, base=base, head=head, branch=branch, **kw)
    except receipt_guard.Unreadable as e:
        say(f"T5 receipt guard could not read the upstream ({e}): no verdict, re-checked on the next run")
        return "unreadable"
    for ln in lines:
        say(f"      {ln}")
    if problems:
        say(f"T5 not eligible on receipts alone: {len(problems)} rule(s)")
        for p in problems:
            say(f"      ✗ {p}")
        return "not_eligible"
    say("T5 eligible: every added recipe carries a PASS receipt that holds on the live upstream")
    if dry_run:
        say(f"T6 dry run: would request merge --auto --match-head-commit {head}")
        return "dry_run"
    demand_canary.request_merge(gh, repo_slug, pr, head)
    say(f"T6 #{pr} merge requested at exact head {head} (lands when every required check is green there)")
    return "merge_requested"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF"))
    ap.add_argument("--base", default=None)
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--today", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repo", type=Path, default=REPO, help="the PR's checkout, read as data (CI: pr/, while this "
                    "script runs from main's checkout)")
    a = ap.parse_args(argv)
    base = a.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    try:
        outcome = decide(pr=a.pr, head=a.head, branch=a.branch or "", base=base, repo_slug=a.repo_slug, today=a.today,
                         env=dict(os.environ), dry_run=a.dry_run, repo=a.repo,
                         autonomy_path=demand_canary.trusted_autonomy(base, a.repo))
    except Unreadable as e:
        print(f"tick canary: cannot act: {e}", file=sys.stderr)
        return 2
    print(f"outcome: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
