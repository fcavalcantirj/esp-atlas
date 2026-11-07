"""Publish the hourly popularity pass without bundling review-required growth.

Called by tick.py before the ordinary growth tick, under scripts/jr-tick.sh's
thermal gate, flock and hard timeout. Uses a separate worktree and a small
GraphQL budget; no LLM, direct-to-main write or runtime database.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import dry_run_tree
import popularity_full
import publish
from budget import Budget

REPO = Path(__file__).resolve().parent.parent
MAX_GRAPHQL_CALLS = 12  # quota probe + ceil(146/25), with bounded catalog growth
MAX_SECONDS = 60.0
SOURCE_REQUEST_TIMEOUT = 8.0
GUARD_TIMEOUT = 60.0
DEFAULT_STATE_FILE = Path(tempfile.gettempdir()) / "jr-popularity-cooldown.json"
BRANCH_PREFIX = "jr/popularity-"


def _load_cooldown(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        until = value.get("cooldown_until") if isinstance(value, dict) else None
        parsed = datetime.fromisoformat(until) if isinstance(until, str) else None
        return parsed.isoformat() if parsed and parsed.tzinfo else None
    except (OSError, TypeError, ValueError):
        return None


def _save_cooldown(path: Path, until: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump({"cooldown_until": until}, tmp)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        temporary = Path(tmp.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _pending_popularity_pr(gh) -> dict | None:
    """Find at most one bot-owned AUTO popularity PR to update with a lease."""
    response = gh("pr", "list", "--state", "open", "--limit", "500", "--json",
                  "number,url,headRefName,headRefOid,baseRefName,labels,author")
    if getattr(response, "returncode", 1) != 0:
        raise RuntimeError("open popularity PR list unavailable")
    try:
        prs = json.loads(response.stdout or "[]")
    except (TypeError, ValueError):
        raise RuntimeError("open popularity PR list unreadable") from None
    if not isinstance(prs, list):
        raise RuntimeError("open popularity PR list malformed")
    pending = [pr for pr in prs if isinstance(pr, dict) and
               str(pr.get("headRefName", "")).startswith(BRANCH_PREFIX) and
               isinstance(pr.get("author"), dict) and
               pr["author"].get("login") == publish.JR_LOGIN]
    if len(pending) > 1:
        raise RuntimeError(f"{len(pending)} pending bot popularity PRs need review")
    if not pending:
        return None
    pr = pending[0]
    if (pr.get("baseRefName") != "main" or
            any((label.get("name") or "").casefold() == "jr-review"
                for label in pr.get("labels") or [] if isinstance(label, dict)) or
            not isinstance(pr.get("url"), str) or
            not isinstance(pr.get("headRefOid"), str)):
        raise RuntimeError("pending popularity PR is not an AUTO main-base bot PR")
    return pr


def default_guard(root: Path) -> dict:
    """Validate the isolated popularity tree; CI runs required tests on the PR."""
    from tick import guard_env

    try:
        response = subprocess.run([sys.executable, "scripts/validate.py"], cwd=root,
                                  capture_output=True, text=True, timeout=GUARD_TIMEOUT,
                                  env=guard_env(root))
        return {"ok": response.returncode == 0,
                "output": (response.stdout + response.stderr).strip()[-2000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"popularity guard exceeded {GUARD_TIMEOUT:.0f}s"}


def run(*, now: datetime | None = None, dry_run: bool = False,
        git=publish.default_git, gh=publish.default_gh, guard=None,
        repo_slug: str | None = None, auto_merge: bool = True,
        budget: Budget | None = None, state_file: Path | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    guard = guard or default_guard
    budget = budget or Budget(max_calls=MAX_GRAPHQL_CALLS, max_seconds=MAX_SECONDS)
    state_file = state_file or Path(os.environ.get("JR_POPULARITY_STATE_FILE", DEFAULT_STATE_FILE))
    if not state_file.is_absolute() or state_file.resolve().is_relative_to(REPO):
        return {"ok": False, "when": now.isoformat(), "stage": None, "publish": None,
                "reason": "popularity cooldown state must be outside the repository",
                "graphql_budget": budget.summary(), "all_gh_calls": 0}
    result: dict = {"ok": False, "when": now.isoformat(), "stage": None,
                    "publish": None, "reason": "", "graphql_budget": ""}
    wt = None
    scratch = None
    observed_calls = 0

    def observed_gh(*args):
        nonlocal observed_calls
        observed_calls += 1
        if gh is publish.default_gh and args[:2] == ("api", "graphql"):
            try:
                return subprocess.run(["gh", *args], cwd=REPO, capture_output=True,
                                      text=True, timeout=SOURCE_REQUEST_TIMEOUT)
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(["gh", *args], 124, "",
                                                   f"GraphQL source request exceeded {SOURCE_REQUEST_TIMEOUT:.0f}s")
        return gh(*args)

    try:
        slug = repo_slug
        if slug is None:
            remote = git("remote", "get-url", "origin")
            slug = publish.owner_repo(getattr(remote, "stdout", "") or "")
        protection = publish.protection_status(slug, gh=observed_gh)
        if not protection.ok:
            result["reason"] = "branch protection: " + protection.reason
            return result
        if dry_run:
            scratch = dry_run_tree.copy(REPO)
            root, base_sha = scratch, "dry-run-local-copy"
        else:
            wt = publish.add_worktree(git=git)
            if not publish.is_clean(wt, git=git):
                result["reason"] = "fresh popularity worktree is not clean"
                return result
            root, base_sha = wt.path, wt.base_sha
        ctx = SimpleNamespace(root=root, now=now, gh=budget.wrap(observed_gh),
                              budget=budget, dry_run=dry_run, base_sha=base_sha,
                              cooldown_until=_load_cooldown(state_file))
        stage = popularity_full.run(ctx)
        result["stage"] = stage.summary
        result["coverage"] = next((item["coverage"] for item in stage.items
                                   if isinstance(item, dict) and "coverage" in item), {})
        coverage = result["coverage"]
        complete_attempt = coverage.get("eligible_repositories") == coverage.get("attempted_repositories")
        result["complete_attempt"] = complete_attempt
        result["receipt"] = str(popularity_full.RECEIPT_DIR / (now.strftime("%Y-%m-%dT%H") + ".json"))
        cooldowns = [item.get("cooldown_until") for item in stage.items
                     if isinstance(item, dict) and item.get("cooldown_until")]
        if cooldowns:
            result["cooldown_until"] = max(cooldowns)
            if not dry_run:
                _save_cooldown(state_file, result["cooldown_until"])
        if dry_run:
            result["ok"] = complete_attempt
            result["would_write"] = len(stage.would_write)
            return result
        verdict = guard(root)
        if not verdict.get("ok"):
            result["reason"] = "guard red: " + str(verdict.get("output") or "")[-300:]
            return result
        pending = _pending_popularity_pr(observed_gh)
        result["pending_pr"] = pending.get("url") if pending else None
        body = ("Deterministic hourly full-catalog popularity pass; no LLM.\n\n"
                f"Base: `{base_sha}`. {stage.summary}\n\n"
                f"Per-record attempted/failure/age receipt: `{result['receipt']}`. "
                "The receipt is proposed, not a deployed freshness claim.\n\n"
                "Only field-exact cited GitHub popularity changes and this receipt are staged. "
                "Identity, floor, review routing, validation and required branch checks remain gates.\n\n"
                f"GraphQL source-read budget: {budget.summary()}. Publication API calls are "
                "counted separately in the runner log; no source-read retries.")
        branch = pending["headRefName"] if pending else BRANCH_PREFIX + now.strftime("%Y%m%d-%H%M")
        subject = "feat(jr): popularity " + now.strftime("%Y-%m-%d %H:%M") + " UTC"
        published = publish.publish(wt, stage.paths, subject, body, git=git, gh=observed_gh,
                                    now=now, repo_slug=slug, protection=protection,
                                    auto_merge=auto_merge, branch=branch,
                                    existing_pr_url=pending["url"] if pending else None,
                                    expected_head_sha=pending["headRefOid"] if pending else None,
                                    stages=[{"name": stage.name, "paths": list(stage.paths),
                                             "needs_human": False}])
        result["publish"] = published.as_dict()
        result["ok"] = published.published and complete_attempt
        result["reason"] = published.reason + ("; incomplete repository attempt coverage" if not complete_attempt else "")
        return result
    except Exception as exc:  # a failed popularity pass must not hide the growth tick's result
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        if wt is not None:
            try:
                publish.remove_worktree(wt, git=git)
                if result.get("publish") and result["publish"].get("branch"):
                    publish.cleanup_branch(result["publish"]["branch"], git=git)
            except Exception as exc:
                result["reason"] += f"; cleanup failed: {type(exc).__name__}: {exc}"
                result["ok"] = False
        if scratch is not None:
            dry_run_tree.remove(scratch)
        result["graphql_budget"] = budget.summary()
        result["all_gh_calls"] = observed_calls


def render_line(result: dict) -> str:
    status = ("HOLD" if result.get("stage") is None else
              "INCOMPLETE" if not result.get("complete_attempt") else
              "PR" if result["ok"] else "HOLD")
    pub = result.get("publish") or {}
    pr = pub.get("pr_url") or "no PR"
    return (f"jr-popularity {status}: {result.get('stage') or result.get('reason')} · "
            f"{pr} · {result.get('graphql_budget')} · all gh calls {result.get('all_gh_calls')}")
