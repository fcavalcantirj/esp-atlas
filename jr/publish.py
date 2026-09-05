"""EspAtlas Jr — the publisher (jr/publish.py): worktree in, pull request out.

Phase 2 of the rebuild. This is the ONLY place the hourly tick touches git or GitHub, and it is
built around the failure that caused the 2026-09-02 incident: jr/drain_pr.py ran
`git checkout -B <branch>` inside a shared, dirty clone, never fetched, and never returned to
main — one run produced two collision PRs of +1464/−1741 over 170 files. Every rule here is a
direct answer to that:

1. **Never the checked-out tree.** A tick gets a fresh `git worktree` detached at
   `origin/main` (after `git fetch origin main`), writes there, and the worktree is removed when
   the tick ends. The clone's own checkout is never read, written, switched or committed.
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
5. **No git command ever names `main` as a write target.** The only `main`s in this module are
   `fetch origin main`, `worktree add --detach … origin/main` and `gh pr create --base main`.

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

REPO = Path(__file__).resolve().parent.parent
REQUIRED_CHECKS = ("schema", "tests", "jr-tests")
PROTECTED_PREFIXES = ("data/firmware/", "data/recipes/")


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
    """A detached worktree at origin/main. `path` is where the tick's stages write."""
    path: Path
    base_sha: str


def add_worktree(git=default_git, root: Path | None = None) -> Worktree:
    """`git fetch origin main` then `git worktree add --detach <dir> origin/main`. The directory
    lives OUTSIDE the repo tree (a temp dir) so no glob over the repo can ever see it. Raises
    RuntimeError if either command fails — a tick must not proceed on a stale base."""
    p = git("fetch", "origin", "main")
    if not _ok(p):
        raise RuntimeError(f"git fetch origin main failed: {getattr(p, 'stderr', '')!s:.200}")
    git("worktree", "prune")          # a tick killed mid-run (SIGKILL) may have left a stale entry
    directory = Path(root or tempfile.mkdtemp(prefix="jr-tick-"))
    p = git("worktree", "add", "--detach", str(directory), "origin/main")
    if not _ok(p):
        shutil.rmtree(directory, ignore_errors=True)    # never leak the temp dir
        raise RuntimeError(f"git worktree add failed: {getattr(p, 'stderr', '')!s:.200}")
    sha = git("rev-parse", "origin/main")
    return Worktree(path=directory, base_sha=(getattr(sha, "stdout", "") or "").strip())


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


def protection_status(repo_slug: str, gh=default_gh,
                      required: tuple = REQUIRED_CHECKS) -> ProtectionStatus:
    """Read the LIVE branch-protection rule on main and the repo's auto-merge switch. ok only
    when every name in `required` is a required status check AND auto-merge is allowed. A 404
    ("Branch not protected") is the exact hole this exists to catch."""
    p = gh("api", f"repos/{repo_slug}/branches/main/protection")
    if not _ok(p):
        err = (getattr(p, "stderr", "") or "") + (getattr(p, "stdout", "") or "")
        if "403" in err or "Resource not accessible" in err:
            return ProtectionStatus(False, reason="cannot read main's protection (403: token lacks permission)")
        return ProtectionStatus(False, reason="main is not protected (auto-merge would merge instantly)")
    try:
        rule = json.loads(p.stdout)
    except (json.JSONDecodeError, TypeError):
        return ProtectionStatus(False, reason="unreadable protection rule")
    rsc = rule.get("required_status_checks") or {}
    contexts = list(rsc.get("contexts") or []) + [c.get("context") for c in (rsc.get("checks") or []) if c.get("context")]
    missing = [c for c in required if c not in contexts]
    q = gh("api", f"repos/{repo_slug}", "-q", ".allow_auto_merge")
    allow = _ok(q) and (getattr(q, "stdout", "") or "").strip().lower() == "true"
    if missing:
        return ProtectionStatus(False, tuple(contexts), allow,
                                reason=f"main does not require {', '.join(missing)}")
    if not allow:
        return ProtectionStatus(False, tuple(contexts), allow, reason="repo has allow_auto_merge off")
    return ProtectionStatus(True, tuple(contexts), allow, reason="")


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

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _staged_deletions(wt: Worktree, git) -> list[str]:
    """Paths staged as deletions. `--no-renames`: git's default rename detection would report a
    deleted record whose content moved to a new id as `R100 old new`, hiding the deletion from
    the G2 check. `-z`: NUL-separated, so a non-ASCII path is never C-quoted into a mismatch."""
    p = git("-C", str(wt.path), "diff", "--cached", "--name-status", "--no-renames", "-z")
    fields = [f for f in (getattr(p, "stdout", "") or "").split("\0")]
    deleted, i = [], 0
    while i + 1 < len(fields):
        status, path = fields[i], fields[i + 1]
        if status.startswith("D") and path:
            deleted.append(path)
        i += 2
    return deleted


def publish(wt: Worktree, paths: list[str], subject: str, body: str, *,
            git=default_git, gh=default_gh, now: datetime | None = None,
            repo_slug: str | None = None, needs_human: bool = False,
            protection: ProtectionStatus | None = None) -> PublishResult:
    """Stage `paths` (+ the ledger) in the worktree, commit, push a fresh `jr/tick-…` branch, open
    the PR, and request auto-merge only when allowed (see the module docstring). Returns a
    PublishResult; never raises for a normal "nothing to publish" or a refused deletion."""
    now = now or datetime.now(timezone.utc)
    branch = branch_name(now)
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
    deleted = _staged_deletions(wt, git)
    protected = [d for d in deleted if d.startswith(PROTECTED_PREFIXES)]
    if protected:
        git("-C", str(wt.path), "reset", "-q", "--", *pathspec)
        return PublishResult(False, branch=branch, paths=pathspec,
                             reason=f"deletion refused (G2 guard not in CI): {', '.join(protected)}")

    # 3. branch, commit, push — on the worktree, never on the clone's checkout
    p = git("-C", str(wt.path), "checkout", "-q", "-B", branch)   # -B: a same-minute retry must not die
    if not _ok(p):
        return PublishResult(False, branch=branch, paths=pathspec, reason="could not create branch")
    p = git("-C", str(wt.path), "commit", "-q", "-m", subject)
    if not _ok(p):
        return PublishResult(False, branch=branch, paths=pathspec, reason="commit failed")
    sha = (getattr(git("-C", str(wt.path), "rev-parse", "HEAD"), "stdout", "") or "").strip()
    p = git("-C", str(wt.path), "push", "-u", "origin", branch)
    if not _ok(p):
        return PublishResult(False, branch=branch, commit=sha, paths=pathspec, reason="push failed")

    # 4. PR
    pr = gh("pr", "create", "--base", "main", "--head", branch, "--title", subject, "--body", body)
    if not _ok(pr):
        return PublishResult(False, branch=branch, commit=sha, paths=pathspec, reason="pr create failed")
    pr_url = (getattr(pr, "stdout", "") or "").strip()

    # 5. auto-merge only when the gate is real and nothing asks for a human
    if needs_human:
        return PublishResult(True, branch, sha, pr_url, False, pathspec, reason="needs_human: auto-merge withheld")
    if deleted:
        return PublishResult(True, branch, sha, pr_url, False, pathspec,
                             reason=f"deletions outside data/: auto-merge withheld ({', '.join(deleted)})")
    if protection is None:
        if repo_slug is None:
            remote = (getattr(git("remote", "get-url", "origin"), "stdout", "") or "").strip()
            repo_slug = owner_repo(remote)
        protection = protection_status(repo_slug, gh=gh)
    if not protection.ok:
        return PublishResult(True, branch, sha, pr_url, False, pathspec,
                             reason=f"auto-merge withheld: {protection.reason}")
    am = gh("pr", "merge", pr_url, "--auto", "--squash")
    if not _ok(am):
        return PublishResult(True, branch, sha, pr_url, False, pathspec, reason="gh pr merge --auto failed")
    return PublishResult(True, branch, sha, pr_url, True, pathspec)


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
