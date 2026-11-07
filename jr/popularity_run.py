"""Publish the hourly popularity pass without bundling review-required growth.

Called by tick.py before the ordinary growth tick, under scripts/jr-tick.sh's
thermal gate, flock and hard timeout. Uses a separate worktree and a small
GraphQL budget; no LLM, direct-to-main write or runtime database.

Before any recovery, delivery, source read, worktree or publication it reads the
same pending-PR index the growth tick does (jr/pending_prs.py): a firmware an OPEN
Jr tick PR already changes is deferred, never rewritten; an inventory that may miss
such a hold fails closed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import dry_run_tree
import pending_prs
import popularity_delivery
import popularity_full
import publish
from budget import Budget

REPO = Path(__file__).resolve().parent.parent
MAX_GRAPHQL_CALLS = 12  # quota probe + ceil(146/25), with bounded catalog growth
MAX_SECONDS = 60.0
SOURCE_REQUEST_TIMEOUT = 8.0
GUARD_TIMEOUT = 60.0
MAX_RUN_SECONDS = 210.0  # leave 390s of the 600s wrapper for growth and overhead
PUBLICATION_RESERVE = 30.0
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
              all(isinstance(row, dict) and row.get("state") in
                  {"pending", "merged", "deployed", "invalidated", "readback_verified",
                   "deployed_no_count_change", "closed", "superseded"}
                  for row in value["deliveries"]))) and
            ("published_head" not in value or isinstance(value["published_head"], dict)) and
            ("publication_intent" not in value or isinstance(value["publication_intent"], dict)))


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

    The PR author and a normal fast-forward push alone cannot establish
    provenance: a human commit already on the branch at lookup time would be
    included unless the previously published head was pinned independently.
    Lost or corrupt local state therefore blocks refresh until reviewed.
    """
    pin = _load_state(path).get("published_head")
    return (isinstance(pin, dict) and pin.get("url") == pending.get("url") and
            pin.get("branch") == pending.get("headRefName") and
            pin.get("sha") == pending.get("headRefOid"))


def _save_publication_intent(path: Path, *, sha: str, branch: str, paths: list[str],
                             samples: list[dict], receipt: str, subject: str, body: str,
                             existing_pr_url: str | None, expected_head_sha: str | None,
                             now: datetime) -> None:
    if not isinstance(sha, str) or len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise ValueError("new popularity commit lacks full SHA")
    value = _load_state(path)
    if value.get("publication_intent"):
        raise RuntimeError("unrecovered popularity publication intent exists")
    value["publication_intent"] = {"sha": sha, "branch": branch, "paths": paths,
                                   "samples": samples, "receipt": receipt,
                                   "subject": subject, "body": body,
                                   "existing_pr_url": existing_pr_url,
                                   "expected_head_sha": expected_head_sha,
                                   "started_at": now.isoformat()}
    _write_state(path, value)


def _clear_publication_intent(path: Path) -> None:
    value = _load_state(path)
    value.pop("publication_intent", None)
    _write_state(path, value)


def _save_published_head(path: Path, published: publish.PublishResult, *,
                         samples: list[dict], now: datetime, receipt: str) -> None:
    if not published.commit or len(published.commit) != 40 or \
            any(ch not in "0123456789abcdef" for ch in published.commit):
        raise ValueError("published popularity head lacks full commit SHA")
    value = _load_state(path)
    intent = value.get("publication_intent")
    if not isinstance(intent, dict) or intent.get("sha") != published.commit or \
            intent.get("branch") != published.branch:
        raise RuntimeError("publication intent does not match the remote PR")
    value["published_head"] = {"url": published.pr_url, "branch": published.branch,
                               "sha": published.commit}
    popularity_delivery.register(value, published, samples, now, receipt)
    del value["publication_intent"]
    _write_state(path, value)


class RecoveryDeferred(Exception):
    """An orphan popularity branch changes a record an OPEN Jr tick PR holds: no PR is opened,
    its intent and branch stay untouched for review."""


def _open_holds(paths, index: pending_prs.PendingIndex) -> list[str]:
    """The OPEN holds (`#pr: firmware`) on the firmware a set of changed paths names."""
    holds = [index.hold(fid) for fid in sorted(pending_prs.firmware_ids(paths))]
    return [f"{h.pr_ref}: {h.firmware}" for h in holds if h is not None and h.state == pending_prs.OPEN]


def _check_orphan_holds(intent: dict, index: pending_prs.PendingIndex, git) -> None:
    """Refuse to open a PR for an orphan branch that edits an OPEN-held record.

    Checks the saved intent paths, then what the pushed branch really changes since it left
    main; a branch diff git cannot list counts as held. The diff is skipped only when no
    record is OPEN-held at all."""
    branch = intent["branch"]
    held = _open_holds(intent["paths"], index)
    if not held and any(h.state == pending_prs.OPEN for h in index.holds.values()):
        diff = None
        if getattr(git("fetch", "origin", f"refs/heads/{branch}"), "returncode", 1) == 0:
            diff = git("diff", "--name-only", f"origin/main...{intent['sha']}")
        if getattr(diff, "returncode", 1) != 0:
            raise RecoveryDeferred(f"orphan branch {branch} changes unreadable")
        held = _open_holds((diff.stdout or "").splitlines(), index)
    if held:
        raise RecoveryDeferred(f"orphan branch {branch} changes a record an open Jr tick PR holds ("
                               + ", ".join(held) + ")")


def _recover_publication_intent(path: Path, gh, git, *, index: pending_prs.PendingIndex) -> str | None:
    """Resolve a durable pre-push intent against exact remote branch/PR state.

    A process may stop after push or PR creation. Never infer success from a
    branch name alone; only the recorded commit can become a delivery. An
    orphan exact branch can be given an unarmed PR unless it edits a record
    `index` shows an OPEN Jr tick PR holding (RecoveryDeferred); any ambiguity
    stays on disk and blocks the next publication for review.
    """
    intent = _load_state(path).get("publication_intent")
    if intent is None:
        return None
    if not isinstance(intent, dict):
        raise RuntimeError("publication intent malformed")
    sha, branch = intent.get("sha"), intent.get("branch")
    if not isinstance(sha, str) or len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha) or \
            not isinstance(branch, str) or not branch.startswith(BRANCH_PREFIX) or \
            not isinstance(intent.get("paths"), list) or not isinstance(intent.get("samples"), list):
        raise RuntimeError("publication intent lacks exact commit or paths")
    url = intent.get("existing_pr_url")
    recovered_state = "OPEN"
    if url:
        response = gh("pr", "view", url, "--json", "url,state,headRefOid,author")
        if getattr(response, "returncode", 1) != 0:
            raise RuntimeError("pending PR unavailable during publication recovery")
        try:
            pr = json.loads(response.stdout or "")
        except (TypeError, ValueError):
            raise RuntimeError("pending PR unreadable during publication recovery") from None
        if not isinstance(pr, dict) or pr.get("url") != url or \
                (pr.get("author") or {}).get("login") != publish.JR_LOGIN:
            raise RuntimeError("pending PR identity changed during publication recovery")
        if pr.get("headRefOid") == intent.get("expected_head_sha") and pr.get("state") == "OPEN":
            _clear_publication_intent(path)  # push never happened
            return "discarded unpushed intent"
        if pr.get("headRefOid") != sha or pr.get("state") not in ("OPEN", "MERGED"):
            raise RuntimeError("pending PR head changed during publication recovery")
        recovered_url = url
        recovered_state = pr["state"]
    else:
        response = gh("pr", "list", "--state", "all", "--head", branch, "--limit", "100",
                      "--json", "url,state,headRefOid,author")
        if getattr(response, "returncode", 1) != 0:
            raise RuntimeError("PR search unavailable during publication recovery")
        try:
            prs = json.loads(response.stdout or "")
        except (TypeError, ValueError):
            raise RuntimeError("PR search unreadable during publication recovery") from None
        if not isinstance(prs, list) or len(prs) > 1:
            raise RuntimeError("PR search ambiguous during publication recovery")
        if prs:
            pr = prs[0]
            if not isinstance(pr, dict) or pr.get("headRefOid") != sha or \
                    pr.get("state") not in ("OPEN", "MERGED") or \
                    (pr.get("author") or {}).get("login") != publish.JR_LOGIN or \
                    not isinstance(pr.get("url"), str):
                raise RuntimeError("remote PR differs from persisted publication intent")
            recovered_url = pr["url"]
            recovered_state = pr["state"]
        else:
            remote = git("ls-remote", "origin", f"refs/heads/{branch}")
            if getattr(remote, "returncode", 1) != 0:
                raise RuntimeError("remote branch unreadable during publication recovery")
            lines = (getattr(remote, "stdout", "") or "").strip().splitlines()
            if not lines:
                _clear_publication_intent(path)  # no remote effect
                return "discarded unpushed intent"
            if len(lines) != 1 or lines[0].split() != [sha, f"refs/heads/{branch}"]:
                raise RuntimeError("remote branch differs from persisted publication intent")
            _check_orphan_holds(intent, index, git)
            created = gh("pr", "create", "--draft", "--base", "main", "--head", branch,
                         "--title", intent.get("subject") or "", "--body", intent.get("body") or "")
            if getattr(created, "returncode", 1) != 0:
                raise RuntimeError("exact pushed branch lacks PR; recovery creation failed")
            recovered_url = (getattr(created, "stdout", "") or "").strip()
            if not recovered_url.startswith("https://github.com/"):
                raise RuntimeError("recovery PR URL unreadable")
    if recovered_state == "OPEN":
        labelled, why = publish.apply_review_label(recovered_url, gh=gh)
        if not labelled:
            raise RuntimeError(f"recovered open PR needs jr-review label: {why}")
    published = publish.PublishResult(True, branch=branch, commit=sha, pr_url=recovered_url,
                                      paths=intent["paths"])
    try:
        when = datetime.fromisoformat(intent["started_at"])
    except (KeyError, TypeError, ValueError):
        when = datetime.now(timezone.utc)
    _save_published_head(path, published, samples=intent["samples"], now=when,
                         receipt=intent.get("receipt") or "")
    return f"recovered exact popularity PR {recovered_url} at {sha}"


def _pending_popularity_pr(gh) -> dict | None:
    """Find at most one bot-owned AUTO popularity PR to update without rewriting."""
    response = gh("pr", "list", "--state", "open", "--limit", "500", "--json",
                  "number,url,headRefName,headRefOid,baseRefName,labels,author,isDraft")
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
    if (pr.get("baseRefName") != "main" or pr.get("isDraft") is True or
            any((label.get("name") or "").casefold() == "jr-review"
                for label in pr.get("labels") or [] if isinstance(label, dict)) or
            not isinstance(pr.get("url"), str) or
            not isinstance(pr.get("headRefOid"), str)):
        raise RuntimeError("pending popularity PR is not an AUTO main-base bot PR")
    return pr


def load_pending(gh, now: datetime, slug: str) -> pending_prs.PendingIndex | None:
    """The growth tick's own pending-PR index: its open-PR list, then pending_prs.load unchanged.
    None when the open list is unreadable; the caller fails closed on that and on any gap."""
    from tick import OPEN_PR_LIMIT, _list_open_prs

    open_prs = _list_open_prs(gh)
    if open_prs is None:
        return None
    return pending_prs.load(gh, open_prs, now, slug=slug, open_limit=OPEN_PR_LIMIT)


def _held_in_branch(wt, index: pending_prs.PendingIndex, git) -> list[str] | None:
    """The OPEN holds (`#pr: firmware`) a reused popularity branch already changes against main.

    An earlier hour's commit stays on that branch; republishing it would land an edit of a
    record a Jr tick PR now changes. None when git cannot list what the branch changes."""
    p = git("-C", str(wt.path), "diff", "--name-only", wt.base_sha, "HEAD")
    if getattr(p, "returncode", 1) != 0:
        return None
    return _open_holds((p.stdout or "").splitlines(), index)


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
        fetch=None, revalidate=publish.revalidate_catalog, clock=time.monotonic) -> dict:
    now = now or datetime.now(timezone.utc)
    overall_started = clock()
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
    source_window_started = False

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
        slug = repo_slug
        if slug is None:
            remote = git("remote", "get-url", "origin")
            slug = publish.owner_repo(getattr(remote, "stdout", "") or "")
        pending_index = load_pending(observed_gh, now, slug)
        if pending_index is None or not pending_index.complete:
            gaps = "; ".join(pending_index.gaps) if pending_index is not None else "Jr PR list unreadable"
            result["reason"] = ("pending-PR inventory incomplete, nothing queried, staged or published: "
                                + gaps)
            return result
        if not dry_run:
            try:
                recovered = _recover_publication_intent(state_file, observed_gh, git,
                                                        index=pending_index)
                if recovered:
                    result["recovery"] = recovered
            except RecoveryDeferred as exc:
                result["recovery"] = f"deferred: {exc}"
                result["reason"] = f"publication recovery deferred: {exc}; preserve intent and branch for review"
                return result
            except Exception as exc:
                result["reason"] = f"publication recovery held: {type(exc).__name__}: {exc}"
                return result
            try:
                result["delivery"] = popularity_delivery.reconcile(
                    state_file, load_state=_load_state, write_state=_write_state,
                    gh=observed_gh, git=git, secret=os.environ.get("REVALIDATE_SECRET"),
                    fetch=fetch, revalidate=revalidate, now=now)
            except Exception as exc:
                result["delivery_error"] = f"{type(exc).__name__}: {exc}"
        protection = publish.protection_status(slug, gh=observed_gh)
        if not protection.ok:
            result["reason"] = "branch protection: " + protection.reason
            return result
        pending = None if dry_run else _pending_popularity_pr(observed_gh)
        result["pending_pr"] = pending.get("url") if pending else None
        if pending and not _pinned_head(state_file, pending):
            result["reason"] = "pending popularity PR head lacks matching local bot publication pin; preserve branch for review"
            return result
        if clock() - overall_started > MAX_RUN_SECONDS - MAX_SECONDS - GUARD_TIMEOUT - PUBLICATION_RESERVE:
            result["reason"] = "overall popularity runtime reserve exhausted before source pass; eligible records deferred"
            return result
        if dry_run:
            scratch = dry_run_tree.copy(REPO)
            root, base_sha = scratch, "dry-run-local-copy"
        else:
            wt = publish.add_worktree(git=git)
            if pending:
                publish.prepare_existing_popularity_worktree(
                    wt, pending["headRefName"], pending["headRefOid"], git=git)
                held = _held_in_branch(wt, pending_index, git)
                if held is None or held:
                    result["reason"] = ("pending popularity PR " + (
                        "changes unreadable" if held is None else
                        "already changes a record an open Jr tick PR holds (" + ", ".join(held) + ")")
                        + "; preserve branch for review")
                    return result
            if not publish.is_clean(wt, git=git):
                result["reason"] = "fresh popularity worktree is not clean"
                return result
            root, base_sha = wt.path, wt.base_sha
        ctx = SimpleNamespace(root=root, now=now, gh=budget.wrap(observed_gh),
                              budget=budget, dry_run=dry_run, base_sha=base_sha,
                              cooldown_until=_load_cooldown(state_file), pending=pending_index)
        budget.start_window()
        source_window_started = True
        stage = popularity_full.run(ctx)
        result["stage"] = stage.summary
        result["coverage"] = next((item["coverage"] for item in stage.items
                                   if isinstance(item, dict) and "coverage" in item), {})
        coverage = result["coverage"]
        # A record an open Jr tick PR holds was not attempted: the pass is incomplete until it is.
        complete_attempt = (coverage.get("eligible_repositories") == coverage.get("attempted_repositories")
                            and coverage.get(popularity_full.DEFERRED_OPEN) == 0)
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
        if clock() - overall_started > MAX_RUN_SECONDS - GUARD_TIMEOUT - PUBLICATION_RESERVE:
            result["reason"] = "overall popularity runtime reserve exhausted before guard; staged values unpublished"
            return result
        verdict = guard(root)
        if not verdict.get("ok"):
            result["reason"] = "guard red: " + str(verdict.get("output") or "")[-300:]
            return result
        if clock() - overall_started > MAX_RUN_SECONDS - PUBLICATION_RESERVE:
            result["reason"] = "overall popularity runtime reserve exhausted before publication; staged values unpublished"
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
        samples = popularity_delivery.expected_samples(root, stage.paths)

        def on_committed(sha, commit_branch, paths):
            _save_publication_intent(state_file, sha=sha, branch=commit_branch, paths=paths,
                                     samples=samples, receipt=result["receipt"], subject=subject,
                                     body=body, existing_pr_url=pending["url"] if pending else None,
                                     expected_head_sha=pending["headRefOid"] if pending else None,
                                     now=now)

        def on_pr_ready(url, sha, pr_branch, paths):
            saved = publish.PublishResult(True, branch=pr_branch, commit=sha, pr_url=url,
                                          paths=paths)
            _save_published_head(state_file, saved, samples=samples, now=now,
                                 receipt=result["receipt"])

        published = publish.publish(wt, stage.paths, subject, body, git=git, gh=observed_gh,
                                    now=now, repo_slug=slug, protection=protection,
                                    auto_merge=auto_merge, branch=branch,
                                    existing_pr_url=pending["url"] if pending else None,
                                    expected_head_sha=pending["headRefOid"] if pending else None,
                                    on_committed=on_committed, on_pr_ready=on_pr_ready,
                                    stages=[{"name": stage.name, "paths": list(stage.paths),
                                             "needs_human": False}])
        result["publish"] = published.as_dict()
        result["ok"] = published.published and complete_attempt
        deferred = coverage.get(popularity_full.DEFERRED_OPEN)
        result["reason"] = published.reason + (
            "" if complete_attempt else "; incomplete repository attempt coverage"
            + (f" ({deferred} deferred to an open Jr tick PR)" if deferred else ""))
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
        result["graphql_budget"] = (budget.summary() if source_window_started else
                                    f"gh calls {budget.calls}/{budget.max_calls} · source window not started")
        result["all_gh_calls"] = observed_calls
        result["overall_seconds"] = round(clock() - overall_started, 1)


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
            + (f" · recovery {result['recovery']}" if result.get("recovery") else "")
            + (f" · delivery {delivery_note}" if delivery_note else ""))
