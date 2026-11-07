"""EspAtlas Jr — the publisher (jr/publish.py): worktree in, pull request out.

Phase 2 of the rebuild. This is the ONLY place the hourly tick touches git or GitHub, and it is
built around the failure that caused the 2026-09-02 incident: jr/drain_pr.py ran
`git checkout -B <branch>` inside a shared, dirty clone, never fetched, and never returned to
main — one run produced two collision PRs of +1464/−1741 over 170 files. Every rule here is a
direct answer to that:

1. **Never the checked-out tree.** A tick gets a fresh `git worktree` detached at the ONE commit
   `origin/main` resolved to (after `git fetch origin main`), writes there, and the worktree is
   removed when the tick ends. Its reported base is its own verified HEAD, never a second read of
   `origin/main` (a concurrent fetch may have moved it). The clone's own checkout is never read, written, switched or committed.
2. **Pathspec only.** `git add -- <paths>` with the exact paths the stages report, plus the
   ledger (memory.staged_paths()). Nothing else in the worktree can reach a commit, however it
   got there.
3. **Additive until the G2 guard exists.** A staged deletion under `data/firmware/` or
   `data/recipes/` is REFUSED — no commit, no PR — because no record may be deleted until
   `scripts/g2_guard.py` gates it in CI (Phase 6). Deletions elsewhere (state files) are allowed
   but withhold auto-merge.
4. **Branch protection is the gate.** With no protection on `main`, `gh pr merge --auto` merges
   immediately (verified on #103), so "PR + auto-merge" would silently be direct-to-main.
   `protection_status()` reads the live rule; auto-merge is requested ONLY when `main` requires
   `schema`, `tests` and `jr-tests` AND the repo allows auto-merge. Otherwise the PR still opens
   and a human merges — bot proposes, CI disposes, human may veto.
5. **Risky changes wait for the owner.** jr/review_routing.py classifies the STAGED diff; a
   `review` route labels the PR `jr-review` and never requests auto-merge — even when the label
   itself cannot be applied (fail closed; the result says so). SPEC-jr-review-routing.md.
6. **No git command ever names `main` as a write target.** The only `main`s in this module are
   `fetch origin main`, `rev-parse --verify origin/main^{commit}` and `gh pr create --base main`.

`git` and `gh` are injectable callables `(*argv) -> object with returncode/stdout/stderr`, so the
whole sequence is unit-tested with recorders and no test ever runs a real git or gh command.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import memory
import review_routing

REPO = Path(__file__).resolve().parent.parent
REQUIRED_CHECKS = ("schema", "tests", "jr-tests")
PROTECTED_PREFIXES = ("data/firmware/", "data/recipes/")
_SHA_RE = re.compile(r"[0-9a-f]{7,64}")


def default_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def default_gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True)


def branch_name(now: datetime | None = None) -> str:
    """jr/tick-YYYYMMDD-HHMM in UTC — one branch per tick."""
    now = now or datetime.now(timezone.utc)
    return f"jr/tick-{now.strftime('%Y%m%d-%H%M')}"


def owner_repo(remote_url: str) -> str:
    """'owner/repo' from an HTTPS or SSH GitHub remote URL."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?/?$", remote_url.strip())
    if not m:
        raise ValueError(f"not a GitHub remote: {remote_url!r}")
    return f"{m.group(1)}/{m.group(2)}"


def _ok(p) -> bool:
    return getattr(p, "returncode", 1) == 0


# --- worktree lifecycle -----------------------------------------------------------------------

@dataclass
class Worktree:
    """A detached worktree at the commit origin/main resolved to (`base_sha`, its verified HEAD).
    `path` is where the tick's stages write."""
    path: Path
    base_sha: str


def add_worktree(git=default_git, root: Path | None = None) -> Worktree:
    """`git fetch origin main`, resolve origin/main to ONE commit, then `git worktree add --detach
    <dir> <that commit>`. The directory lives OUTSIDE the repo tree (a temp dir) so no glob over the
    repo can ever see it. `base_sha` is the worktree's own HEAD, required to equal the resolved
    commit: a concurrent fetch moving origin/main mid-call can never make the run report a revision
    it did not mine. Raises RuntimeError when any step fails — a tick must not proceed on a stale
    or unknown base."""
    p = git("fetch", "origin", "main")
    if not _ok(p):
        raise RuntimeError(f"git fetch origin main failed: {getattr(p, 'stderr', '')!s:.200}")
    git("worktree", "prune")          # a tick killed mid-run (SIGKILL) may have left a stale entry
    base = _commit(git("rev-parse", "--verify", "origin/main^{commit}"))
    if not base:
        raise RuntimeError("origin/main does not resolve to a commit")
    directory = Path(root or tempfile.mkdtemp(prefix="jr-tick-"))
    p = git("worktree", "add", "--detach", str(directory), base)
    if not _ok(p):
        shutil.rmtree(directory, ignore_errors=True)    # never leak the temp dir
        raise RuntimeError(f"git worktree add failed: {getattr(p, 'stderr', '')!s:.200}")
    wt = Worktree(path=directory, base_sha=base)
    head = _commit(git("-C", str(directory), "rev-parse", "--verify", "HEAD^{commit}"))
    if head != base:
        remove_worktree(wt, git=git)
        shutil.rmtree(directory, ignore_errors=True)
        raise RuntimeError(f"worktree HEAD {head or 'unreadable'} is not the resolved origin/main {base}")
    return wt


def prepare_existing_popularity_worktree(wt: Worktree, branch: str, expected_head_sha: str,
                                        git=default_git) -> None:
    """Preserve a pending PR's commits and merge current main before refreshing it.

    The local branch must be the exact previously pinned head. A normal push of
    a descendant then rejects concurrent remote changes without rewriting PR
    history. Any fetch, identity or merge uncertainty leaves the PR untouched.
    """
    if not re.fullmatch(r"jr/popularity-[0-9]{8}-[0-9]{4}", branch) or \
            not re.fullmatch(r"[0-9a-f]{40,64}", expected_head_sha):
        raise RuntimeError("pending popularity branch/head malformed")
    ref = f"refs/remotes/origin/{branch}"
    p = git("fetch", "origin", f"refs/heads/{branch}:{ref}")
    if not _ok(p):
        raise RuntimeError("pending popularity branch fetch failed")
    fetched = _commit(git("rev-parse", "--verify", f"{ref}^{{commit}}"))
    if fetched != expected_head_sha:
        raise RuntimeError("pending popularity branch changed before worktree preparation")
    p = git("-C", str(wt.path), "checkout", "-q", "--detach", expected_head_sha)
    if not _ok(p):
        raise RuntimeError("pending popularity head checkout failed")
    p = git("-C", str(wt.path), "merge", "--no-edit", "origin/main")
    if not _ok(p):
        raise RuntimeError("pending popularity branch cannot merge current main cleanly")
    for ancestor in (expected_head_sha, wt.base_sha):
        if not _ok(git("-C", str(wt.path), "merge-base", "--is-ancestor", ancestor, "HEAD")):
            raise RuntimeError("prepared popularity head lacks old PR or current main ancestry")


def _commit(p) -> str:
    """The commit id a successful `rev-parse --verify` printed, or "" — never an arbitrary string."""
    sha = (getattr(p, "stdout", "") or "").strip()
    return sha if _ok(p) and _SHA_RE.fullmatch(sha) else ""


def remove_worktree(wt: Worktree, git=default_git) -> None:
    """Always called, even after a failure — the worktree is disposable by design."""
    git("worktree", "remove", "--force", str(wt.path))
    git("worktree", "prune")


def cleanup_branch(branch: str, git=default_git) -> None:
    """Delete the LOCAL tick branch once its worktree is gone. `checkout -B` inside the worktree
    creates the branch in the clone's shared refs; the remote keeps the pushed copy (the PR), so
    the local ref is clutter that would also collide with a same-minute retry."""
    git("branch", "-D", branch)


def is_clean(wt: Worktree, git=default_git) -> bool:
    p = git("-C", str(wt.path), "status", "--porcelain")
    return _ok(p) and not (getattr(p, "stdout", "") or "").strip()


# --- branch protection preflight -------------------------------------------------------------

@dataclass
class ProtectionStatus:
    ok: bool
    required_checks: tuple = ()
    allow_auto_merge: bool = False
    reason: str = ""
    source: str = ""          # "ruleset" | "protection" — which endpoint answered


def _ruleset_checks(repo_slug: str, gh) -> list[str] | None:
    """Required status checks from the repository RULESETS that apply to main
    (`GET /repos/{o}/{r}/rules/branches/main`) — readable with plain read access, so a write-only
    bot sees the same truth an admin does. None when no active ruleset requires checks (or the
    endpoint is unavailable); then the classic protection endpoint is consulted."""
    r = gh("api", f"repos/{repo_slug}/rules/branches/main")
    if not _ok(r):
        return None
    try:
        rules = json.loads(r.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    contexts: list[str] = []
    for rule in rules if isinstance(rules, list) else []:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            for c in (rule.get("parameters") or {}).get("required_status_checks") or []:
                if isinstance(c, dict) and c.get("context"):
                    contexts.append(c["context"])
    return contexts or None


def protection_status(repo_slug: str, gh=default_gh,
                      required: tuple = REQUIRED_CHECKS) -> ProtectionStatus:
    """Read the LIVE rule that guards main and the repo's auto-merge switch. ok only when every
    name in `required` is a required status check AND auto-merge is allowed.

    Rulesets first (`/rules/branches/main`, readable by any token — the bot is a write
    collaborator and can never read the admin-only classic endpoint); classic branch protection
    second. On the classic endpoint a 404 ("Branch not protected") is the exact hole this exists
    to catch — but GitHub also answers 404 to a write-only token there, so a 404 is cross-checked
    against the lighter `GET /branches/main`: `protected: true` means the rule exists and THIS
    token cannot read its required checks. Auto-merge is withheld either way; only the reason
    differs, and the reason must not lie."""
    contexts = _ruleset_checks(repo_slug, gh)
    if contexts is not None:
        return _decide(repo_slug, gh, required, contexts, source="ruleset")
    p = gh("api", f"repos/{repo_slug}/branches/main/protection")
    if not _ok(p):
        err = (getattr(p, "stderr", "") or "") + (getattr(p, "stdout", "") or "")
        if "403" in err or "Resource not accessible" in err:
            return ProtectionStatus(False, reason="cannot read main's protection (403: token lacks permission)")
        b = gh("api", f"repos/{repo_slug}/branches/main", "-q", ".protected")
        if _ok(b) and (getattr(b, "stdout", "") or "").strip().lower() == "true":
            return ProtectionStatus(False, reason="protection exists but this token cannot read its required checks "
                                                  "(admin-only endpoint answers 404 to a write token; needs Administration: read)")
        return ProtectionStatus(False, reason="main is not protected (auto-merge would merge instantly)")
    try:
        rule = json.loads(p.stdout)
    except (json.JSONDecodeError, TypeError):
        return ProtectionStatus(False, reason="unreadable protection rule")
    rsc = rule.get("required_status_checks") or {}
    contexts = list(rsc.get("contexts") or []) + [c.get("context") for c in (rsc.get("checks") or []) if c.get("context")]
    return _decide(repo_slug, gh, required, contexts, source="protection")


def _decide(repo_slug: str, gh, required: tuple, contexts: list[str], source: str) -> ProtectionStatus:
    missing = [c for c in required if c not in contexts]
    q = gh("api", f"repos/{repo_slug}", "-q", ".allow_auto_merge")
    allow = _ok(q) and (getattr(q, "stdout", "") or "").strip().lower() == "true"
    if missing:
        return ProtectionStatus(False, tuple(contexts), allow, source=source,
                                reason=f"main does not require {', '.join(missing)} ({source})")
    if not allow:
        return ProtectionStatus(False, tuple(contexts), allow, source=source, reason="repo has allow_auto_merge off")
    return ProtectionStatus(True, tuple(contexts), allow, source=source, reason="")


# --- earned trust: auto-merge only after N clean merges, reset by a LABELLED veto ----------------
# A closed-unmerged PR resets trust ONLY when it carries a veto label. A close WITHOUT that label
# is benign by design — a superseded / duplicate / housekeeping close — and is excluded from the
# calculation entirely (neither a merge nor a veto). This is the fix for the "death spiral": one
# incident used to breed a few closes -> trust reset -> auto-merge off -> PRs pile up -> the
# pile-up breeds duplicates -> clearing them forces MORE closes -> trust never re-earned. CI is the
# quality gate (a red-CI PR can't merge anyway); the trust gate is purely human judgement, so only
# a deliberate, LABELLED veto should count. To reject Jr's work, close the PR with the `veto` label.

JR_LOGIN = "espatlas-jr"
TRUST_N = 10
VETO_LABELS = frozenset({"veto"})


@dataclass
class TrustStatus:
    ok: bool
    merged: int = 0     # merges in the last-n non-benign window
    closed: int = 0     # labelled vetoes in that window
    reason: str = ""


def _is_veto(pr: dict) -> bool:
    """A closed-unmerged PR is a veto only if it carries a label whose name (case-insensitive)
    is in VETO_LABELS. Robust to labels being missing / null / [] and to malformed entries."""
    for lab in pr.get("labels") or []:
        if isinstance(lab, dict) and (lab.get("name") or "").lower() in VETO_LABELS:
            return True
    return False


def trust_status(gh=default_gh, login: str = JR_LOGIN, n: int = TRUST_N) -> TrustStatus:
    """Felipe's ladder, automated: Jr earns auto-merge when its last `n` terminal PRs (ignoring
    benign closes) are all MERGED by a human; a single LABELLED veto in that window resets the
    count. Reads GitHub, never a local flag, so the state is the same on every machine and survives
    restarts. Benign closes (duplicate / superseded / housekeeping — no veto label) are dropped
    entirely, so routine tick-PR cleanup can never reset earned trust."""
    fetch_limit = max(n * 3, 30)    # benign closes are filtered out; over-fetch to still find n
    p = gh("pr", "list", "--author", login, "--state", "closed",
           "--limit", str(fetch_limit), "--json", "number,mergedAt,labels")
    if not _ok(p):
        return TrustStatus(False, reason="trust unknown (gh pr list failed)")
    try:
        prs = json.loads(getattr(p, "stdout", "") or "[]")
    except json.JSONDecodeError:
        return TrustStatus(False, reason="trust unknown (unreadable pr list)")
    # Classify in recency order; drop benign closes; take the first n of what remains.
    window: list[bool] = []     # True = merged, False = labelled veto
    for pr in prs:
        if pr.get("mergedAt"):
            window.append(True)
        elif _is_veto(pr):
            window.append(False)
        # else: benign close -> excluded entirely
        if len(window) >= n:
            break
    merged = sum(1 for m in window if m)
    vetoed = len(window) - merged
    if vetoed:
        return TrustStatus(False, merged, vetoed,
                           reason=f"trust reset: {vetoed} of Jr's last {len(window)} terminal PRs were vetoed")
    if merged < n:
        return TrustStatus(False, merged, vetoed, reason=f"trust not yet earned: {merged}/{n} consecutive merges")
    return TrustStatus(True, merged, vetoed, reason="")


# --- publish ----------------------------------------------------------------------------------

@dataclass
class PublishResult:
    published: bool
    branch: str = ""
    commit: str = ""
    pr_url: str = ""
    auto_merge: bool = False
    paths: list = field(default_factory=list)
    reason: str = ""
    route: str = ""                                       # review_routing.REVIEW | AUTO ("" before routing)
    review_reasons: list = field(default_factory=list)
    labelled: bool = False                                # the jr-review label is on the PR

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _staged_status(wt: Worktree, git) -> list[tuple[str, str]]:
    """(status, path) of every staged path. `--no-renames`: git's default rename detection would
    report a deleted record whose content moved to a new id as `R100 old new`, hiding the deletion
    from the G2 check. `-z`: NUL-separated, so a non-ASCII path is never C-quoted into a mismatch."""
    p = git("-C", str(wt.path), "diff", "--cached", "--name-status", "--no-renames", "-z")
    fields = [f for f in (getattr(p, "stdout", "") or "").split("\0")]
    out, i = [], 0
    while i + 1 < len(fields):
        status, path = fields[i], fields[i + 1]
        if status and path:
            out.append((status, path))
        i += 2
    return out


def _staged_deletions(wt: Worktree, git) -> list[str]:
    return [path for status, path in _staged_status(wt, git) if status.startswith("D")]


def _git_text(wt: Worktree, git, rev_path: str) -> str | None:
    p = git("-C", str(wt.path), "show", rev_path)
    return getattr(p, "stdout", None) if _ok(p) else None


def _staged_changes(wt: Worktree, git) -> list:
    """The staged diff as review_routing.Change entries. A modified data/**.md record carries its
    HEAD and index text, so the classifier can tell a star/date refresh from a content edit."""
    changes = []
    for status, path in _staged_status(wt, git):
        old = new = None
        if status.startswith("M") and path.startswith("data/") and path.endswith(".md"):
            old, new = _git_text(wt, git, f"HEAD:{path}"), _git_text(wt, git, f":{path}")
        changes.append(review_routing.Change(path, status, old, new))
    return changes


def _err(p) -> str:
    return (getattr(p, "stderr", "") or "").strip()[:120]


def apply_review_label(pr_url: str, gh=default_gh, repo_slug: str | None = None) -> tuple[bool, str]:
    """Put the jr-review label on the PR; returns (labelled, why-not). The label is ensured first
    (`label create --force` is idempotent, so a failure there is noted, not fatal — the label may
    already exist), then `gh pr edit --add-label`; if that fails, once more through the REST issues
    endpoint, which takes a different path than pr edit's GraphQL mutation."""
    label = review_routing.REVIEW_LABEL
    c = gh("label", "create", label, "--color", review_routing.REVIEW_LABEL_COLOR,
           "--description", review_routing.REVIEW_LABEL_DESCRIPTION, "--force")
    e = gh("pr", "edit", pr_url, "--add-label", label)
    if _ok(e):
        return True, ""
    why = [f"label create: {_err(c)}"] if not _ok(c) else []
    why.append(f"pr edit --add-label: {_err(e)}")
    m = re.search(r"/pull/(\d+)", pr_url)
    if m:
        a = gh("api", "--method", "POST", f"repos/{repo_slug or '{owner}/{repo}'}/issues/{m.group(1)}/labels",
               "-f", f"labels[]={label}")
        if _ok(a):
            return True, ""
        why.append(f"REST issues labels: {_err(a)}")
    return False, "; ".join(why)


def _pr_merge_state(pr_url: str, gh) -> dict | None:
    response = gh("pr", "view", pr_url, "--json", "state,headRefOid,autoMergeRequest")
    if not _ok(response):
        return None
    try:
        state = json.loads(response.stdout or "")
    except (TypeError, ValueError):
        return None
    return state if isinstance(state, dict) and "autoMergeRequest" in state else None


def _ensure_disarmed(pr_url: str, expected_sha: str, gh) -> bool:
    """Observe the exact open head and remove any previously armed auto-merge.

    A missing/unreadable field is uncertainty, not evidence of a safe remote
    state. Re-read after disabling because gh success alone is insufficient.
    """
    state = _pr_merge_state(pr_url, gh)
    if not state or state.get("state") != "OPEN" or state.get("headRefOid") != expected_sha:
        return False
    if state["autoMergeRequest"] is not None:
        if not _ok(gh("pr", "merge", pr_url, "--disable-auto")):
            return False
        state = _pr_merge_state(pr_url, gh)
    return bool(state and state.get("state") == "OPEN" and
                state.get("headRefOid") == expected_sha and state["autoMergeRequest"] is None)


def publish(wt: Worktree, paths: list[str], subject: str, body: str, *,
            git=default_git, gh=default_gh, now: datetime | None = None,
            repo_slug: str | None = None, needs_human: bool = False,
            protection: ProtectionStatus | None = None, auto_merge: bool = True,
            trust: TrustStatus | None = None, branch: str | None = None,
            stages: list | None = None, existing_pr_url: str | None = None,
            expected_head_sha: str | None = None,
            on_committed=None, on_pr_ready=None) -> PublishResult:
    """Stage `paths` (+ the ledger) in the worktree, commit, push a fresh `jr/tick-…` branch (or
    the caller's `branch`, e.g. the daily demand runner's `jr/demand-…`), open the PR, and request
    auto-merge only when allowed (see the module docstring). `stages` are the tick's stage-result
    dicts, read by review_routing (needs_human, device-evidence review items). Returns a
    PublishResult; never raises for a normal "nothing to publish" or a refused deletion."""
    now = now or datetime.now(timezone.utc)
    branch = branch or branch_name(now)
    if existing_pr_url and (not expected_head_sha or not re.fullmatch(r"[0-9a-f]{40,64}", expected_head_sha)):
        return PublishResult(False, branch=branch, reason="existing PR needs an exact expected head SHA")
    pathspec = list(dict.fromkeys([*paths, *memory.staged_paths()]))

    # 1. stage exactly the pathspec; nothing else can reach the commit. git aborts the WHOLE add
    #    (rc 128, nothing staged) when one element matches nothing — that must not read as
    #    "nothing to publish".
    p = git("-C", str(wt.path), "add", "--", *pathspec)
    if not _ok(p):
        return PublishResult(False, branch=branch, paths=pathspec,
                             reason=f"git add failed: {(getattr(p, 'stderr', '') or '').strip()[:160]}")
    if _ok(git("-C", str(wt.path), "diff", "--cached", "--quiet")):
        return PublishResult(False, branch=branch, paths=pathspec, reason="nothing to publish")

    # 2. G2: no record deletion may be committed until the guard exists in CI
    changes = _staged_changes(wt, git)
    deleted = [c.path for c in changes if c.status.startswith("D")]
    protected = [d for d in deleted if d.startswith(PROTECTED_PREFIXES)]
    if protected:
        git("-C", str(wt.path), "reset", "-q", "--", *pathspec)
        return PublishResult(False, branch=branch, paths=pathspec,
                             reason=f"deletion refused (G2 guard not in CI): {', '.join(protected)}")
    route = review_routing.classify(changes, stages or (), needs_human=needs_human)

    # A pending PR may already be armed from a prior run. Disarm and verify
    # before replacing its head; otherwise a later policy veto could inherit
    # an active remote auto-merge request.
    if existing_pr_url and not _ensure_disarmed(existing_pr_url, expected_head_sha, gh):
        return PublishResult(False, branch=branch, paths=pathspec,
                             reason="existing PR head or auto-merge state unsafe before replacement")

    # 3. branch, commit, push — on the worktree, never on the clone's checkout
    p = git("-C", str(wt.path), "checkout", "-q", "-B", branch)   # -B: a same-minute retry must not die
    if not _ok(p):
        return PublishResult(False, branch=branch, paths=pathspec, reason="could not create branch")
    p = git("-C", str(wt.path), "commit", "-q", "-m", subject)
    if not _ok(p):
        return PublishResult(False, branch=branch, paths=pathspec, reason="commit failed")
    sha = (getattr(git("-C", str(wt.path), "rev-parse", "HEAD"), "stdout", "") or "").strip()
    if existing_pr_url and not _ok(git("-C", str(wt.path), "merge-base", "--is-ancestor",
                                   expected_head_sha, "HEAD")):
        return PublishResult(False, branch=branch, commit=sha, paths=pathspec,
                             reason="refreshed PR head is not a descendant of its pinned head")
    if on_committed is not None:
        try:
            on_committed(sha, branch, pathspec)
        except Exception as exc:
            return PublishResult(False, branch=branch, commit=sha, paths=pathspec,
                                 reason=f"publication intent persistence failed: {type(exc).__name__}: {exc}")
    if existing_pr_url:
        # The prepared head contains the prior PR commit. A normal fast-forward
        # push preserves history and rejects any concurrent divergent update.
        p = git("-C", str(wt.path), "push", "origin", branch)
    else:
        p = git("-C", str(wt.path), "push", "-u", "origin", branch)
    if not _ok(p):
        return PublishResult(False, branch=branch, commit=sha, paths=pathspec, reason="push failed")

    # 4. PR
    if existing_pr_url:
        if not _ensure_disarmed(existing_pr_url, sha, gh):
            return PublishResult(False, branch=branch, commit=sha, paths=pathspec,
                                 reason="existing PR changed, closed or armed after fast-forward push")
        edited = gh("pr", "edit", existing_pr_url, "--title", subject, "--body", body)
        if not _ok(edited):
            return PublishResult(False, branch=branch, commit=sha, paths=pathspec,
                                 reason="existing PR body update failed")
        pr_url = existing_pr_url
        if not _ensure_disarmed(pr_url, sha, gh):
            return PublishResult(False, branch=branch, commit=sha, paths=pathspec,
                                 reason="existing PR changed or armed during body update")
    else:
        pr = gh("pr", "create", "--base", "main", "--head", branch, "--title", subject, "--body", body)
        if not _ok(pr):
            return PublishResult(False, branch=branch, commit=sha, paths=pathspec, reason="pr create failed")
        pr_url = (getattr(pr, "stdout", "") or "").strip()

    # Apply a required review label before declaring the PR recoverably
    # published. A crash before this point leaves the durable intent; recovery
    # conservatively labels the PR for review. No unlabelled REVIEW branch can
    # be mistaken for AUTO by the next hourly run.
    labelled = False
    if route.review:
        labelled, why = apply_review_label(pr_url, gh=gh, repo_slug=repo_slug)
        if not labelled:
            return PublishResult(False, branch=branch, commit=sha, pr_url=pr_url, paths=pathspec,
                                 reason=f"jr-review label FAILED ({why}); auto-merge withheld",
                                 route=route.route, review_reasons=list(route.reasons), labelled=False)

    # The durable delivery record must exist before any auto-merge request.
    # If a crash/write failure occurs here, the pre-push intent lets the next
    # scheduled run recover the exact remote PR without inventing delivery.
    if on_pr_ready is not None:
        try:
            on_pr_ready(pr_url, sha, branch, pathspec)
        except Exception as exc:
            return PublishResult(False, branch=branch, commit=sha, pr_url=pr_url, paths=pathspec,
                                 reason=f"publication delivery persistence failed: {type(exc).__name__}: {exc}")

    # 5. risk routing: a review route is labelled and NEVER auto-merges.
    if route.review:
        reason = f"jr-review ({'; '.join(route.reasons)[:300]}): auto-merge withheld"
        if existing_pr_url and not _ensure_disarmed(pr_url, sha, gh):
            return PublishResult(False, branch, sha, pr_url, False, pathspec,
                                 reason=reason + "; remote auto-merge state unsafe", route=route.route,
                                 review_reasons=list(route.reasons), labelled=labelled)
        return PublishResult(True, branch, sha, pr_url, False, pathspec, reason=reason,
                             route=route.route, review_reasons=list(route.reasons), labelled=labelled)

    # 6. auto-merge only when the gate is real
    armed, reason = _auto_merge(pr_url, gh, git, auto_merge, deleted, protection, trust, repo_slug, sha)
    if existing_pr_url:
        remote = _pr_merge_state(pr_url, gh)
        if not remote or remote.get("state") != "OPEN" or remote.get("headRefOid") != sha:
            return PublishResult(False, branch, sha, pr_url, False, pathspec,
                                 reason="existing PR head changed before/after auto-merge decision",
                                 route=route.route)
    if existing_pr_url and not armed and not _ensure_disarmed(pr_url, sha, gh):
        return PublishResult(False, branch, sha, pr_url, False, pathspec,
                             reason=reason + "; remote auto-merge state unsafe", route=route.route)
    return PublishResult(True, branch, sha, pr_url, armed, pathspec, reason=reason, route=route.route)


def _auto_merge(pr_url: str, gh, git, auto_merge: bool, deleted: list, protection, trust,
                repo_slug, expected_sha: str) -> tuple[bool, str]:
    """(auto_merge_armed, reason) for an AUTO-routed PR: the caller, deletions, branch protection
    and earned trust must all allow it before `gh pr merge --auto` is requested."""
    if not auto_merge:
        return False, "auto-merge disabled by the caller (--no-auto-merge)"
    if deleted:
        return False, f"deletions outside data/: auto-merge withheld ({', '.join(deleted)})"
    if protection is None:
        if repo_slug is None:
            remote = (getattr(git("remote", "get-url", "origin"), "stdout", "") or "").strip()
            repo_slug = owner_repo(remote)
        protection = protection_status(repo_slug, gh=gh)
    if not protection.ok:
        return False, f"auto-merge withheld: {protection.reason}"
    trust = trust_status(gh=gh) if trust is None else trust
    if not trust.ok:
        return False, f"auto-merge withheld: {trust.reason}"
    if not _ok(gh("pr", "merge", pr_url, "--auto", "--squash",
                  "--match-head-commit", expected_sha)):
        return False, "gh pr merge --auto failed"
    return True, ""


# --- post-merge cache purge -------------------------------------------------------------------

def revalidate_catalog(secret: str | None, url: str = "https://esp-atlas.com/api/revalidate",
                       http=None, timeout: float = 20.0) -> dict:
    """POST the catalog purge route with the shared secret after a merge that changed records
    (PR 0.5, #112). Never raises: a 503 means the site has no secret configured, a 401 means a
    key mismatch — both are reported, neither blocks the tick. `http(url, headers, timeout)`
    is injectable and must return (status_code, body_text)."""
    if not secret:
        return {"ok": False, "skipped": "no REVALIDATE_SECRET"}
    if http is None:
        def http(u, headers, t):
            import urllib.error
            import urllib.request
            req = urllib.request.Request(u, method="POST", headers=headers, data=b"")
            try:
                with urllib.request.urlopen(req, timeout=t) as r:
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001 — never raise out of a report step
                return 0, f"{type(e).__name__}: {e}"
    status, body = http(url, {"Authorization": f"Bearer {secret}"}, timeout)
    return {"ok": status == 200, "status": status, "body": body[:200]}
