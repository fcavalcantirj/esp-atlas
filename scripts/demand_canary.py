#!/usr/bin/env python3
"""The canary: a demand PR every machine check accepts merges itself (scripts/demand_canary.py).

SPEC-demand-work-consumer.md, "Machine review of a demand PR". A `jr/research-<KEY>` PR used to wait for a
person to read it and click merge (hours: #1706, #1743, #1800). The reading is now three CI jobs — `quotes`
(every quoted span on a cited page), `demand-guard` (the PR changes exactly what its work item says) and
the catalog's own schema/guards — so the click is the only step left, and this job takes it:

  D1  `jr/autonomy.json` has `demand_automerge: true` (turned on by a reviewed PR);
  D2  the repository variable JR_DEMAND_AUTOMERGE is not "0" (the instant kill switch, no PR needed);
  D3  the branch is `jr/research-<KEY>`;
  D4  no other `jr/research-*` PR merged today (UTC): at most ONE demand auto-merge per day;
  D5  the quotes check, run again here on the records this PR changes, has no FAIL and no INCONCLUSIVE —
      a FAIL gets a PR comment naming the quote and the label `needs-human` (the executor's retry sees
      it; nobody waits for a person); an INCONCLUSIVE page is re-checked on the next run of this job;
  D6  then: mark the PR ready and request `gh pr merge --merge --auto --match-head-commit <head>` — the
      merge happens only when every required check is green at EXACTLY this head (jr/publish.py's rule).

Every decision is printed. Exit 0 always except an unreadable input (2): a canary that cannot act is not
a failure of the PR. `--dry-run` decides and prints but neither comments, labels, readies nor merges.

    python3 scripts/demand_canary.py --pr 1800 --head <sha> --branch jr/research-<KEY>   # in Actions
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import check_quotes  # noqa: E402

AUTONOMY = REPO / "jr" / "autonomy.json"
FLAG, VARIABLE = "demand_automerge", "JR_DEMAND_AUTOMERGE"
BRANCH_PREFIX = "jr/research-"
LABEL = "needs-human"
DAILY_CAP = 1


class Unreadable(Exception):
    pass


def default_gh(*args: str) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise Unreadable(f"gh {' '.join(args[:3])}: {p.stderr.strip()[:200]}")
    return p.stdout


def switches(autonomy_path: Path, env: dict, flag: str = FLAG, variable: str = VARIABLE) -> tuple[bool, str]:
    """(on, why) for the two switches: the reviewed file flag AND the kill variable. The tick canary
    (scripts/tick_canary.py) uses the same rule with its own flag and variable."""
    try:
        doc = json.loads(Path(autonomy_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return False, f"D1 {autonomy_path} unreadable ({type(e).__name__}): off"
    if doc.get(flag) is not True:
        return False, f"D1 {flag} is {doc.get(flag)!r} in jr/autonomy.json: off (a reviewed PR turns it on)"
    if str(env.get(variable, "1")).strip() == "0":
        return False, f"D2 repository variable {variable}=0: off (the kill switch)"
    return True, f"D1 {flag} true; D2 {variable} not 0"


def merged_today(gh, repo_slug: str, today: str, prefix: str = BRANCH_PREFIX, label: str | None = None) -> list[str]:
    """Head branches of the `prefix*` PRs merged on `today` (UTC); with `label`, only those carrying it."""
    args = ["pr", "list", "--repo", repo_slug, "--state", "merged", "--search", f"merged:>={today}",
            "--json", "headRefName,mergedAt", "--limit", "50"]
    if label:
        args += ["--label", label]
    out = gh(*args)
    try:
        rows = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        raise Unreadable(f"merged list unparsable: {e}") from e
    return sorted(r["headRefName"] for r in rows
                  if str(r.get("headRefName", "")).startswith(prefix) and str(r.get("mergedAt", ""))[:10] == today)


def quotes_verdict(base: str, fetch=None, repo: Path = REPO) -> tuple[str, list[str]]:
    """('PASS'|'FAIL'|'INCONCLUSIVE'|'NONE', the failing or inconclusive quotes) over the records the PR changes."""
    paths = check_quotes.changed_records(base, repo)
    if paths is None:
        raise Unreadable("the diff for the quotes check could not be taken")
    if fetch is None:
        if check_quotes.httpx is None:
            raise Unreadable("httpx is required to fetch the cited pages")
        client = check_quotes.httpx.Client(timeout=check_quotes.TIMEOUT_SECONDS, headers={"User-Agent": check_quotes.USER_AGENT})
        fetch = lambda url: check_quotes.fetch_page(client, url)  # noqa: E731
    pages: dict = {}
    reports = []
    for path in paths:
        fm, _ = check_quotes.parse_frontmatter(path)
        if check_quotes.quotes_in(fm):
            reports.append(check_quotes.check_record(path, fm, pages, fetch))
    if not reports:
        return "NONE", []
    verdicts = {r.verdict for r in reports}
    if check_quotes.FAIL in verdicts:
        return check_quotes.FAIL, [f'"{q.quote}" ({q.where})' for r in reports for q in r.quotes if q.verdict == check_quotes.FAIL]
    if check_quotes.INCONCLUSIVE in verdicts:
        return check_quotes.INCONCLUSIVE, [f'"{q.quote}" ({q.where})' for r in reports for q in r.quotes if q.verdict == check_quotes.INCONCLUSIVE]
    return check_quotes.PASS, []


def decide(*, pr: int, head: str, branch: str, base: str, repo_slug: str, today: str, env: dict,
           autonomy_path: Path = AUTONOMY, gh=default_gh, fetch=None, repo: Path = REPO, dry_run: bool = False,
           out=None) -> str:
    """Run the decisions D1-D6 and act; returns the one-word outcome: off | not_demand | capped | fail |
    inconclusive | merge_requested | dry_run."""
    out = out or sys.stdout
    say = lambda s: print(s, file=out)  # noqa: E731
    on, why = switches(autonomy_path, env)
    say(why)
    if not on:
        return "off"
    if not (branch or "").startswith(BRANCH_PREFIX):
        say(f"D3 {branch!r} is not a {BRANCH_PREFIX}* branch: not a demand PR")
        return "not_demand"
    say(f"D3 demand PR #{pr} on {branch} at {head}")
    done = merged_today(gh, repo_slug, today)
    if len(done) >= DAILY_CAP:
        say(f"D4 daily cap: {len(done)} demand PR(s) merged today ({', '.join(done)}); this one waits for tomorrow")
        return "capped"
    say(f"D4 daily cap free ({len(done)} merged today)")
    verdict, details = quotes_verdict(base, fetch=fetch, repo=repo)
    if verdict == check_quotes.FAIL:
        say(f"D5 quotes FAIL: {len(details)} quote(s) not on any cited page")
        for d in details:
            say(f"      {d}")
        if not dry_run:
            body = ("Quote check FAILED for this demand PR: the quote(s) below appear on none of the record's cited pages. "
                    "Re-read the page and quote it as written, or omit the claim (cite-or-omit).\n\n" + "\n".join(f"- {d}" for d in details)
                    + f"\n\n`scripts/check_quotes.py` at {head}; label `{LABEL}` set, no auto-merge.")
            gh("pr", "comment", str(pr), "--repo", repo_slug, "--body", body)
            gh("pr", "edit", str(pr), "--repo", repo_slug, "--add-label", LABEL)
        return "fail"
    if verdict == check_quotes.INCONCLUSIVE:
        say(f"D5 quotes INCONCLUSIVE: {len(details)} quote(s) on a page that did not answer; re-checked on the next run")
        for d in details:
            say(f"      {d}")
        return "inconclusive"
    say(f"D5 quotes {verdict}" + (" (no quoted text in the changed records)" if verdict == "NONE" else ""))
    if dry_run:
        say(f"D6 dry run: would mark #{pr} ready and request merge --auto --match-head-commit {head}")
        return "dry_run"
    gh("pr", "ready", str(pr), "--repo", repo_slug)
    gh("pr", "merge", str(pr), "--repo", repo_slug, "--merge", "--auto", "--match-head-commit", head)
    say(f"D6 #{pr} marked ready; merge requested at exact head {head} (lands when every required check is green there)")
    return "merge_requested"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--head", required=True, help="the PR head sha the checks ran on")
    ap.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF"))
    ap.add_argument("--base", default=None)
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    ap.add_argument("--today", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    base = a.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    try:
        outcome = decide(pr=a.pr, head=a.head, branch=a.branch or "", base=base, repo_slug=a.repo_slug, today=a.today,
                         env=dict(os.environ), dry_run=a.dry_run)
    except Unreadable as e:
        print(f"demand canary: cannot act: {e}", file=sys.stderr)
        return 2
    print(f"outcome: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
