"""EspAtlas Jr — keep its own review PRs mergeable (jr/review_refresh.py, SPEC-jr-review-routing.md §8).

Every tick PR edits jr/proposed_ledger.json, so a jr-review PR conflicts with main as soon as any other
tick PR merges, and until now a person resolved it by hand. `refresh(pr)` does that resolution itself,
only inside these limits (owner + reviewer, 2026-11-15):
  - the Jr bot's own same-repo tick PR, labelled jr-review, that GitHub reports CONFLICTING;
  - every commit on it is the bot's (a human commit after the bot's is never touched);
  - the head is still the one the tick listed;
  - the conflict is in bookkeeping files only (the ledger, the board cooldown, docs/telemetry);
  - the ledger becomes memory.merge_pr_ledger(main, merge base, PR head), docs/telemetry/yield.jsonl
    main's rows plus the PR's own (yield_ledger.merge_text), every other bookkeeping file main's;
    scripts/ledger_guard.py is green against main; every catalog file the PR changed is byte-identical
    to its head;
  - the result is a merge commit ON TOP of the PR head, pushed without force (fast-forward only).
Anything else is a skip with the reason; nothing is pushed. A dry run reports what it would do.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import memory
import pending_prs
import review_routing
import yield_ledger
from publish import JR_LOGIN

LEDGER = "jr/proposed_ledger.json"
REPO = Path(__file__).resolve().parent.parent


def _ledger_guard():
    spec = importlib.util.spec_from_file_location("ledger_guard", REPO / "scripts" / "ledger_guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ok(p) -> bool:
    return getattr(p, "returncode", 1) == 0


def _out(p) -> str:
    return (getattr(p, "stdout", "") or "").strip()


def _bot_only(gh, number) -> bool | None:
    """True when every commit on the PR is the Jr bot's; None when unreadable."""
    p = gh("pr", "view", str(number), "--json", "commits")
    if not _ok(p):
        return None
    try:
        commits = json.loads(_out(p) or "{}").get("commits") or []
    except ValueError:
        return None
    logins = [a.get("login") for c in commits for a in (c.get("authors") or []) if isinstance(a, dict)]
    return bool(logins) and all(x == JR_LOGIN for x in logins)


def _show(git, rev_path: str):
    p = git("show", rev_path)
    return _out(p) if _ok(p) else None


def refresh(pr: dict, *, git, gh, now: datetime, dry_run: bool = False, any_route: bool = False) -> dict:
    """`any_route`: the tick's preflight also hands over a STALE CONFLICTING auto-route tick PR (2026-11-25, #2081:
    one halted every tick until a person acted). Every other limit below applies unchanged."""
    n, branch, head = pr.get("number"), pr.get("headRefName"), pr.get("headRefOid")
    out = {"pr": n, "status": "skipped", "why": ""}
    if not pending_prs.eligible(pr):
        return {**out, "why": "not the Jr bot's own tick PR"}
    if not any_route and not review_routing.has_review_label(pr):
        return {**out, "why": "not a jr-review PR"}
    if pr.get("mergeable") != "CONFLICTING":
        return {**out, "why": f"mergeable={pr.get('mergeable')}, nothing to refresh"}
    bot = _bot_only(gh, n)
    if bot is not True:
        return {**out, "why": "commits unreadable" if bot is None else "a human commit is on the PR"}
    if not (_ok(git("fetch", "origin", "main")) and _ok(git("fetch", "origin", branch))):
        return {**out, "why": "fetch failed"}
    if _out(git("rev-parse", "FETCH_HEAD")) != head:
        return {**out, "why": "the head moved since the tick listed it"}
    base = _out(git("merge-base", head, "origin/main"))
    if not base:
        return {**out, "why": "no merge base"}
    wt = Path(tempfile.mkdtemp(prefix="jr-refresh-"))
    try:
        if not _ok(git("worktree", "add", "--detach", str(wt), head)):
            return {**out, "why": "worktree add failed"}
        g = lambda *a: git("-C", str(wt), *a)  # noqa: E731
        g("merge", "--no-commit", "--no-ff", "origin/main")
        conflicted = [x for x in _out(g("diff", "--name-only", "--diff-filter=U")).splitlines() if x]
        content = [x for x in conflicted if not review_routing.is_bookkeeping(x)]
        if content or not conflicted:
            g("merge", "--abort")
            return {**out, "why": f"content conflict: {', '.join(content[:3])}" if content else "no conflict to resolve"}
        main_doc = json.loads(_show(git, f"origin/main:{LEDGER}") or "{}")
        merged = None
        for path in conflicted:
            if path == LEDGER:
                merged = memory.merge_pr_ledger(main_doc, json.loads(_show(git, f"{base}:{LEDGER}") or "{}"),
                                                json.loads(_show(git, f"{head}:{LEDGER}") or "{}"), now=now)
                (wt / LEDGER).write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            elif path == yield_ledger.RELPATH:      # append-only rows: the PR's own tick must reach main
                (wt / path).write_text(yield_ledger.merge_text(_show(git, f"origin/main:{path}") or "",
                                                               _show(git, f"{head}:{path}") or ""), encoding="utf-8")
            else:
                g("checkout", "origin/main", "--", path)
            g("add", "--", path)
        if merged is not None and _ledger_guard().check(main_doc, merged):
            g("merge", "--abort")
            return {**out, "why": "ledger guard red on the merged ledger"}
        pr_data = [x for x in _out(git("diff", "--name-only", base, head, "--", "data/")).splitlines() if x]
        for path in pr_data:
            if _out(g("rev-parse", f":{path}")) != _out(git("rev-parse", f"{head}:{path}")):
                g("merge", "--abort")
                return {**out, "why": f"catalog file changed by the merge: {path}"}
        if dry_run:
            g("merge", "--abort")
            return {**out, "status": "would_refresh", "why": f"{len(conflicted)} bookkeeping conflict(s)"}
        if not _ok(g("commit", "--no-edit", "-m", f"chore(jr): refresh #{n} against main (SPEC-jr-review-routing.md §8)")):
            return {**out, "why": "commit failed"}
        new = _out(g("rev-parse", "HEAD"))
        if not _ok(g("push", "origin", f"HEAD:refs/heads/{branch}")):      # never --force: fast-forward only
            return {**out, "why": "push refused (not a fast-forward)"}
        return {**out, "status": "refreshed", "why": f"{len(conflicted)} bookkeeping conflict(s)", "head": new}
    finally:
        git("worktree", "remove", "--force", str(wt))
        shutil.rmtree(wt, ignore_errors=True)
