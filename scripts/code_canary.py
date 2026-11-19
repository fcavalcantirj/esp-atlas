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

`--sweep` gives the same decision to every open PR that has a verdict for its current head: the hourly
catch-up for a PASS the cap made wait and for a verdict whose canary run never answered.

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
# never merged by the machine, whatever the verdict: the switches, CI itself, the canaries and guards, the reviewer
# and its contract (4th review of #1809, 2026-11-19: an agent-PASSed PR could otherwise switch automation on)
HUMAN_ONLY = ("jr/autonomy.json", ".github/", "scripts/code_canary.py", "scripts/demand_canary.py",
              "scripts/tick_canary.py", "scripts/demand_guard.py", "scripts/receipt_guard.py", "scripts/ledger_guard.py",
              "scripts/jr_pr_guard.py", "scripts/validate_main.py", "jr/agent_review.py", "docs/REVIEW-CONTRACT.md",
              "docs/ops/REVIEW-PROMPT.md")


def human_only_paths(gh, repo_slug: str, pr: int) -> list[str] | None:
    """The PR's changed paths a canary may never merge; None when the list cannot be seen whole."""
    try:
        doc = json.loads(gh("pr", "view", str(pr), "--repo", repo_slug, "--json", "files,changedFiles") or "{}")
    except json.JSONDecodeError:
        return None
    files = [f.get("path", "") for f in (doc.get("files") or []) if isinstance(f, dict)]
    if not files or int(doc.get("changedFiles") or 0) != len(files):
        return None
    return [p for p in files if any(p == h or (h.endswith("/") and p.startswith(h)) for h in HUMAN_ONLY)]
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
    """What already used this hour's merge: PRs merged in the last 60 minutes that carry agent-pass, and open
    PRs that carry it (a merge already requested). Both are REST list reads, never the search API: `gh pr
    list --label` goes through the search index, which lags a label written seconds earlier, so two decisions
    in one job could both see the cap free (review BLOCK of #1871, 2026-11-19)."""
    since = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = gh("api", f"repos/{repo_slug}/pulls?state=closed&base=main&sort=updated&direction=desc&per_page=100")
    queued = gh("api", f"repos/{repo_slug}/issues?state=open&labels={PASS_LABEL}&per_page=100")
    try:
        rows, waiting = json.loads(out or "[]"), json.loads(queued or "[]")
        if not isinstance(rows, list) or not isinstance(waiting, list):
            raise TypeError("not a list")
        names = lambda r: {str(x.get("name")) for x in r.get("labels") or []}  # noqa: E731
        return ([f"#{r.get('number')}" for r in rows
                 if str(r.get("merged_at") or "") >= since and PASS_LABEL in names(r)]
                + [f"#{r.get('number')} (queued)" for r in waiting if "pull_request" in r])
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        raise Unreadable(f"merged list unparsable: {e}") from e


def decide(*, pr: int, head: str, verdict_json: str | None, repo_slug: str, now: datetime, env: dict,
           autonomy_path: Path = demand_canary.AUTONOMY, gh=demand_canary.default_gh, dry_run: bool = False,
           out=None, cap_used: tuple = ()) -> str:
    """`cap_used`: merges this very process already requested or saw queued (the sweep passes them), counted
    on top of what GitHub reports, so one job never requests two merges whatever a read returns."""
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
    held = human_only_paths(gh, repo_slug, pr)
    if held is None or held:
        say("C3b " + ("the changed files cannot be listed whole" if held is None else
                      f"touches {', '.join(held[:5])}") + f": a human merges this one; label {HUMAN_LABEL}")
        if not dry_run:
            gh("pr", "edit", str(pr), "--repo", repo_slug, "--add-label", HUMAN_LABEL)
        return "human_only"
    done = sorted(set(merged_last_hour(gh, repo_slug, now)) | set(cap_used))
    if len(done) >= HOURLY_CAP:
        say(f"C4 hourly cap: {', '.join(done)} merged in the last hour; this one waits for the next run")
        return "capped"
    say("C4 hourly cap free")
    if dry_run:
        say(f"C5 dry run: would label {PASS_LABEL} and request merge --auto --match-head-commit {head}")
        return "dry_run"
    gh("pr", "edit", str(pr), "--repo", repo_slug, "--add-label", PASS_LABEL)
    try:
        gh("pr", "merge", str(pr), "--repo", repo_slug, "--merge", "--auto", "--match-head-commit", head)
    except Exception:
        # the label alone would read as a merge already requested and hold the hourly cap for every PR
        try:
            gh("pr", "edit", str(pr), "--repo", repo_slug, "--remove-label", PASS_LABEL)
        except Exception:  # noqa: BLE001 — the sweep drops a label with no merge behind it
            pass
        raise
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


def sweep(*, repo_slug: str, now: datetime, env: dict, autonomy_path: Path = demand_canary.AUTONOMY,
          gh=demand_canary.default_gh, dry_run: bool = False, out=None) -> dict:
    """{pr number: outcome} for every open PR that has a verdict for its CURRENT head: the same decision a
    marker comment gets, for the verdicts nobody acted on (the hourly cap printed "waits for the next run" and
    there was none; a canary run that crashed answered nothing). Oldest PR first. Left alone: drafts, forks, a
    PR whose merge is really requested, a verdict for another head. A BLOCK or a human-only PASS that already
    carries its label costs no write. An agent-pass label with no auto-merge behind it is dropped and the PR
    decided again. Every merge requested or found queued here counts against the cap for the rest of the
    sweep. One unreadable PR never stops the others; switches off -> {} and no call."""
    out = out or sys.stdout
    on, why = demand_canary.switches(autonomy_path, env, flag=FLAG, variable=VARIABLE)
    if not on:
        print(f"sweep: off ({why})", file=out)
        return {}
    try:
        prs = json.loads(gh("pr", "list", "--repo", repo_slug, "--state", "open", "--base", "main", "--limit", "300",
                            "--json", "number,isDraft,isCrossRepository,labels,autoMergeRequest") or "[]")
    except json.JSONDecodeError as e:
        raise Unreadable(f"open PR list unparsable: {e}") from e
    prs = sorted((p for p in prs if not p.get("isDraft") and not p.get("isCrossRepository")),
                 key=lambda p: int(p.get("number") or 0))
    labels = {int(p["number"]): {str(x.get("name")) for x in p.get("labels") or []} for p in prs}
    used = tuple(f"#{p['number']} (queued)" for p in prs
                 if PASS_LABEL in labels[int(p["number"])] and p.get("autoMergeRequest"))
    results = {}
    for pr in prs:
        n = int(pr["number"])
        try:
            if PASS_LABEL in labels[n]:
                if pr.get("autoMergeRequest"):
                    results[n] = "queued"               # merge really requested; it lands when its checks do
                    continue
                print(f"sweep: #{n} carries {PASS_LABEL} with no merge requested; dropping the label", file=out)
                if not dry_run:
                    gh("pr", "edit", str(n), "--repo", repo_slug, "--remove-label", PASS_LABEL)
            head, vj = verdict_from_comments(gh, repo_slug, n)
            if vj is None:
                continue
            is_pass = json.loads(vj).get("verdict") == "PASS"
            if not is_pass and HUMAN_LABEL in labels[n]:
                results[n] = "block_known"
            elif is_pass and HUMAN_LABEL in labels[n] and human_only_paths(gh, repo_slug, n) != []:
                results[n] = "human_only_known"
            else:
                print(f"sweep: #{n} at {head[:8]}", file=out)
                results[n] = decide(pr=n, head=head, verdict_json=vj, repo_slug=repo_slug, now=now, env=env,
                                    autonomy_path=autonomy_path, gh=gh, dry_run=dry_run, out=out, cap_used=used)
                if results[n] == "merge_requested":
                    used += (f"#{n}",)
        except Exception as e:  # noqa: BLE001 — Unreadable, a gh failure: this PR waits, the others do not
            results[n] = f"unreadable: {str(e)[:160]}"
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int)
    ap.add_argument("--sweep", action="store_true",
                    help="decide on every open PR that has a verdict for its current head (the hourly catch-up)")
    ap.add_argument("--head", help="the exact head (default: the PR's current head when --from-comments)")
    ap.add_argument("--author", default="")
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--from-comments", action="store_true",
                    help="read the newest marker verdict comment for the PR's current head instead of VERDICT_JSON")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.sweep == (a.pr is not None):
        ap.error("give exactly one of --pr and --sweep")
    if a.sweep:
        try:
            results = sweep(repo_slug=a.repo_slug, now=datetime.now(timezone.utc), env=dict(os.environ),
                            autonomy_path=demand_canary.AUTONOMY, gh=demand_canary.default_gh, dry_run=a.dry_run)
        except Exception as e:  # noqa: BLE001 — a catch-up that cannot read GitHub tries again next hour
            print(f"sweep: unavailable: {str(e)[:200]}")
            return 0
        for n, outcome in results.items():
            print(f"sweep: #{n} {outcome}")
        print(f"sweep: {len(results)} PR(s) with a verdict for their head")
        return 0
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
