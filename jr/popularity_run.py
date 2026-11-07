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
import popularity_delivery
import popularity_full
import publish
from budget import Budget

REPO = Path(__file__).resolve().parent.parent
MAX_GRAPHQL_CALLS = 12  # quota probe + ceil(146/25), with bounded catalog growth
MAX_SECONDS = 60.0
SOURCE_REQUEST_TIMEOUT = 8.0
GUARD_TIMEOUT = 60.0
DEFAULT_STATE_FILE = Path.home() / ".local/state/esp-atlas/jr-popularity.json"
BRANCH_PREFIX = "jr/popularity-"


def _load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def _state_integrity(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    return (isinstance(value, dict) and
            ("deliveries" not in value or
             (isinstance(value["deliveries"], list) and
              all(isinstance(row, dict) for row in value["deliveries"]))) and
            ("published_head" not in value or isinstance(value["published_head"], dict)))


def _load_cooldown(path: Path) -> str | None:
    try:
        until = _load_state(path).get("cooldown_until")
        parsed = datetime.fromisoformat(until) if isinstance(until, str) else None
        return parsed.isoformat() if parsed and parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _write_state(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(value, tmp, sort_keys=True)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        temporary = Path(tmp.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_cooldown(path: Path, until: str) -> None:
    value = _load_state(path)
    value["cooldown_until"] = until
    _write_state(path, value)


def _pinned_head(path: Path, pending: dict) -> bool:
    """Only a head this runner previously published may be replaced.

    The PR author and a force-with-lease alone cannot establish provenance: a
    human commit already on the branch at lookup time would satisfy the lease.
    Lost or corrupt local state therefore blocks refresh until reviewed.
    """
    pin = _load_state(path).get("published_head")
    return (isinstance(pin, dict) and pin.get("url") == pending.get("url") and
            pin.get("branch") == pending.get("headRefName") and
            pin.get("sha") == pending.get("headRefOid"))


def _save_published_head(path: Path, published: publish.PublishResult, *, root: Path,
                         paths: list[str], now: datetime, receipt: str) -> None:
    if not published.commit or len(published.commit) != 40 or \
            any(ch not in "0123456789abcdef" for ch in published.commit):
        raise ValueError("published popularity head lacks full commit SHA")
    value = _load_state(path)
    value["published_head"] = {"url": published.pr_url, "branch": published.branch,
                               "sha": published.commit}
    popularity_delivery.register(value, published, popularity_delivery.expected_samples(root, paths),
                                 now, receipt)
    _write_state(path, value)


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
        budget: Budget | None = None, state_file: Path | None = None,
        fetch=None, revalidate=publish.revalidate_catalog) -> dict:
    now = now or datetime.now(timezone.utc)
    guard = guard or default_guard
    budget = budget or Budget(max_calls=MAX_GRAPHQL_CALLS, max_seconds=MAX_SECONDS)
    state_file = state_file or Path(os.environ.get("JR_POPULARITY_STATE_FILE", DEFAULT_STATE_FILE))
    if not state_file.is_absolute() or state_file.resolve().is_relative_to(REPO):
        return {"ok": False, "when": now.isoformat(), "stage": None, "publish": None,
                "reason": "popularity cooldown state must be outside the repository",
                "graphql_budget": budget.summary(), "all_gh_calls": 0}
    if not _state_integrity(state_file):
        return {"ok": False, "when": now.isoformat(), "stage": None, "publish": None,
                "reason": "persistent popularity state unreadable; preserve pending PR and delivery history",
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
            except subprocess.TimeoutExpired as exc:
                # The response may already contain HTTP 429 and Retry-After.
                # Keep those bytes for cooldown parsing, while _call rejects
                # every timed-out repository payload as incomplete.
                return subprocess.CompletedProcess(["gh", *args], 124, exc.stdout or b"",
                                                   exc.stderr or b"")
        return gh(*args)

    try:
        if not dry_run:
            try:
                result["delivery"] = popularity_delivery.reconcile(
                    state_file, load_state=_load_state, write_state=_write_state,
                    gh=observed_gh, git=git, secret=os.environ.get("REVALIDATE_SECRET"),
                    fetch=fetch, revalidate=revalidate, now=now)
            except Exception as exc:
                result["delivery_error"] = f"{type(exc).__name__}: {exc}"
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
        if pending and not _pinned_head(state_file, pending):
            result["reason"] = "pending popularity PR head lacks matching local bot publication pin; preserve branch for review"
            return result
        body = ("Deterministic hourly full-catalog popularity pass; no LLM.\n\n"
                f"Base: `{base_sha}`. {stage.summary}\n\n"
                f"Per-record attempted/failure/age receipt: `{result['receipt']}`. "
                "The receipt is proposed, not a deployed freshness claim.\n\n"
                "Only field-exact cited GitHub popularity changes and this receipt are staged. "
                "Identity, floor, review routing, validation and required branch checks remain gates.\n\n"
                f"GraphQL source-read budget: {budget.summary()}. The runner separately counts gh CLI "
                "invocations, which are not an HTTP request count; provider quota deltas require natural "
                "runtime observation. No source-read retries.")
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
        if published.published and published.pr_url and published.commit:
            _save_published_head(state_file, published, root=root, paths=stage.paths,
                                 now=now, receipt=result["receipt"])
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
    deliveries = result.get("delivery") or []
    delivery_note = ", ".join(
        f"{row.get('pr_url', '').rsplit('/', 1)[-1]}:{row.get('state')}"
        + (f"({str(row.get('reason'))[:80]})" if row.get("reason") else "")
        for row in deliveries[-3:] if isinstance(row, dict))
    if result.get("delivery_error"):
        delivery_note += f" error:{result['delivery_error']}"
    return (f"jr-popularity {status}: {result.get('stage') or result.get('reason')} · "
            f"{pr} · {result.get('graphql_budget')} · gh CLI invocations {result.get('all_gh_calls')}"
            + (f" · delivery {delivery_note}" if delivery_note else ""))
