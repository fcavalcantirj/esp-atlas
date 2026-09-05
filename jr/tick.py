"""EspAtlas Jr — the hourly tick (jr/tick.py). Phase 2 skeleton: everything but the content.

    python3 jr/tick.py --dry-run          # gauge + allocation + "nothing to do"; writes nothing
    python3 jr/tick.py                    # the real thing (hermes cron `jr-tick`, via scripts/jr-tick.sh)

One tick, in order (PLAN §3.2):

 1. Preflight — GitHub rate limit ≥ 500 remaining; no Jr tick PR open longer than 3 h; branch
    protection on `main` requires schema + tests + jr-tests and auto-merge is allowed. Any of
    these red → the tick ABORTS before touching anything. Protection missing is the one that
    matters most: without it "PR + auto-merge" is direct-to-main under another name.
 2. Worktree — a fresh `git worktree` detached at `origin/main`, outside the repo tree. Every
    read and write below happens there. The clone's checkout is never touched. (jr/publish.py)
 3. Memory — expire TTL'd decisions; settle proposed PRs (closed → permanent rejection,
    merged → merged); mark ledger ids now in the catalog as merged; a merged id that vanished
    from the catalog becomes a permanent rejection. (jr/memory.py) If anything merged or was
    removed, purge the site's catalog cache (POST /api/revalidate, PR 0.5).
 4. Gauge — scripts/data_completion.compute_completion over the worktree's data/.
 5. Allocation — Phase 2 has NO content stages, so it logs `A0/B0`. Phase 5's allocator
    replaces this line with the gauge-driven split.
 6. Stages — pluggable `Stage` callables (Phase 3: admission/discovery; Phase 4: board mapping;
    Phase 5: Track A). Each returns the paths it wrote under the worktree. STAGES is empty here.
 7. Guard once — only if something was written: `scripts/validate.py` in the worktree, then the
    CI regression tests. Red → the worktree is discarded, nothing is published, the report says so.
 8. Publish — pathspec-only commit on `jr/tick-…`, push, PR, auto-merge only when the gate is
    real and no stage asked for a human. (jr/publish.py)
 9. Report — ONE line, always, to stdout and Telegram. (jr/report.py)
10. The worktree is removed in `finally`, whatever happened.

Every external effect is injectable (git, gh, gauge, guard, notifier, pr_state, revalidate,
clock) so the whole tick runs under pytest with recorders and never touches git, GitHub, the
network or the real data/ tree.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import memory   # noqa: E402
import publish  # noqa: E402
import report   # noqa: E402
from budget import Budget, BudgetExceeded  # noqa: E402

REPO = _JR_DIR.parent
MIN_RATE_LIMIT = 500
STALE_PR_HOURS = 3.0
TICK_BRANCH_PREFIX = "jr/tick-"


class TickAbort(RuntimeError):
    """A preflight or guard verdict that stops the tick. Reported, never raised out of run_tick."""


# --- stage protocol ----------------------------------------------------------------------------

@dataclass
class TickContext:
    """What a stage gets: where to write (the worktree root), the ledger path inside it, a
    counted `gh`, the clock, and the budget. Stages write ONLY under `root` and return the paths
    they wrote relative to it."""
    root: Path
    ledger_path: Path
    now: datetime
    gh: Callable
    git: Callable
    budget: Budget
    dry_run: bool
    env: dict


@dataclass
class StageResult:
    name: str
    paths: list = field(default_factory=list)      # repo-relative paths written under ctx.root
    summary: str = ""
    needs_human: bool = False
    admitted: int = 0
    rejects: dict = field(default_factory=dict)    # reason -> count


Stage = Callable[[TickContext], StageResult]
STAGES: list = []   # Phase 3+ appends here; Phase 2 ships none, so a tick can never write.


# --- defaults for the injectable effects -------------------------------------------------------

def default_gauge(data_dir: Path) -> dict:
    sys.path.insert(0, str(REPO / "scripts"))
    import data_completion  # noqa: E402
    return data_completion.compute_completion(str(data_dir))


def default_guard(root: Path) -> dict:
    """validate.py once, then the CI regression tests — both in the worktree, never the clone."""
    v = subprocess.run([sys.executable, "scripts/validate.py"], cwd=root, capture_output=True,
                       text=True, timeout=300)
    if v.returncode != 0:
        return {"ok": False, "output": (v.stdout + v.stderr).strip()[-2000:]}
    t = subprocess.run([sys.executable, "-m", "pytest", "apps/core/tests/test_coverage_matrix.py",
                        "apps/core/tests/test_examples.py", "apps/core/tests/test_intent_oracle.py", "-q"],
                       cwd=root, capture_output=True, text=True, timeout=600)
    return {"ok": t.returncode == 0, "output": (t.stdout + t.stderr).strip()[-2000:]}


def default_notifier(text: str) -> dict:
    import notify
    return notify.send_telegram(text)


# --- preflight ---------------------------------------------------------------------------------

def _rate_limit_remaining(gh) -> int | None:
    p = gh("api", "rate_limit", "-q", ".resources.core.remaining")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        return int((p.stdout or "").strip())
    except (ValueError, AttributeError):
        return None


def _stale_tick_pr(gh, now: datetime, hours: float) -> str | None:
    p = gh("pr", "list", "--state", "open", "--json", "number,createdAt,headRefName")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        prs = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for pr in prs:
        if not str(pr.get("headRefName", "")).startswith(TICK_BRANCH_PREFIX):
            continue
        try:
            created = datetime.fromisoformat(str(pr.get("createdAt", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - created).total_seconds() > hours * 3600:
            return f"#{pr.get('number')} ({pr.get('headRefName')})"
    return None


def _repo_slug(git) -> str:
    p = git("remote", "get-url", "origin")
    return publish.owner_repo((getattr(p, "stdout", "") or "").strip())


# --- the tick ----------------------------------------------------------------------------------

def run_tick(*, dry_run: bool = False, git=publish.default_git, gh=publish.default_gh,
             now: datetime | None = None, env: dict | None = None, stages: list | None = None,
             gauge=default_gauge, guard=default_guard, notifier=default_notifier,
             pr_state=None, revalidate=publish.revalidate_catalog, budget: Budget | None = None,
             repo_slug: str | None = None, min_rate_limit: int = MIN_RATE_LIMIT,
             stale_pr_hours: float = STALE_PR_HOURS, telegram: bool = True) -> report.TickReport:
    now = now or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    budget = budget or Budget()
    gh_c = budget.wrap(gh)
    r = report.TickReport(when=now, dry_run=dry_run)
    stages = STAGES if stages is None else stages
    wt = None
    try:
        # 1. preflight
        remaining = _rate_limit_remaining(gh_c)
        if remaining is None:
            raise TickAbort("gh unavailable (rate_limit query failed)")
        if remaining < min_rate_limit:
            raise TickAbort(f"GitHub rate limit low: {remaining} < {min_rate_limit}")
        stale = _stale_tick_pr(gh_c, now, stale_pr_hours)
        if stale:
            raise TickAbort(f"a Jr tick PR has been open > {stale_pr_hours:g} h: {stale}")
        slug = repo_slug or _repo_slug(git)
        protection = publish.protection_status(slug, gh=gh_c)
        if not protection.ok:
            if dry_run:
                r.warnings.append(f"branch protection: {protection.reason}")
            else:
                raise TickAbort(f"branch protection: {protection.reason}")

        # 2. worktree (real runs only); dry-run reads the clone's tree and writes nothing
        if dry_run:
            root, ledger_path = REPO, memory.DEFAULT_LEDGER_PATH
        else:
            wt = publish.add_worktree(git=git)
            if not publish.is_clean(wt, git=git):
                raise TickAbort("fresh worktree is not clean")
            root, ledger_path = wt.path, wt.path / "jr" / "proposed_ledger.json"
            r.base_sha = wt.base_sha[:7]

        # 3. memory
        catalogued = {p.parent.name for p in (root / "data" / "firmware").glob("*/firmware.md")}
        if dry_run:
            r.memory = {}
            r.warnings.append("memory: dry-run, no reconciliation written")
        else:
            expired = memory.expire(path=ledger_path, now=now)
            state_fn = pr_state or (lambda ref: memory.gh_pr_state(ref, gh=gh_c))
            settled = memory.reconcile_prs(state_fn, path=ledger_path, now=now)
            merged = memory.reconcile_merged(catalogued, path=ledger_path, now=now)
            removed = memory.reconcile_removed(catalogued, path=ledger_path, now=now)
            r.memory = {"expired": len(expired), "merged": len(settled["merged"]) + len(merged),
                        "rejected": len(settled["rejected"]), "removed": len(removed)}
            if settled["merged"] or merged or removed:
                r.revalidate = revalidate(env.get("REVALIDATE_SECRET"))

        # 4. gauge
        g = gauge(root / "data")
        r.boards_pct = float(g.get("entities", {}).get("boards", {}).get("pct", 0.0))
        r.overall_pct = float(g.get("overall_pct", 0.0))

        # 5. allocation (Phase 5 replaces)
        r.allocation = f"boards {r.boards_pct:.1f}% -> A0/B0 (phase 2: no content stages)"

        # 6. stages
        ctx = TickContext(root=root, ledger_path=ledger_path, now=now, gh=gh_c, git=git,
                          budget=budget, dry_run=dry_run, env=env)
        for stage in stages:
            res = stage(ctx)
            r.stages.append({"name": res.name, "paths": list(res.paths), "summary": res.summary,
                             "needs_human": res.needs_human})
            r.admitted += res.admitted
            for k, v in res.rejects.items():
                r.rejects[k] = r.rejects.get(k, 0) + v

        # 7. guard once, 8. publish — only when something was written, never on a dry run
        if r.paths and not dry_run:
            r.guard = guard(root)
            if not r.guard.get("ok"):
                raise TickAbort("guard red — worktree discarded, nothing published")
            subject = f"feat(jr): tick {now.strftime('%Y-%m-%d %H:%M')} UTC — {len(r.paths)} path(s)"
            res = publish.publish(wt, r.paths, subject, report.render_pr_body(r), git=git, gh=gh_c,
                                  now=now, repo_slug=slug, needs_human=r.needs_human,
                                  protection=protection)
            r.publish = res.as_dict()
    except BudgetExceeded as e:
        r.aborted = f"budget: {e}"
    except TickAbort as e:
        r.aborted = str(e)
    except Exception as e:  # noqa: BLE001 — a tick must always end with a report line
        r.aborted = f"{type(e).__name__}: {e}"
    finally:
        if wt is not None:
            publish.remove_worktree(wt, git=git)
        r.budget = budget.summary()

    line = report.render_line(r)
    print(line)
    if telegram and not dry_run and notifier is not None:
        try:
            notifier(line)
        except Exception:  # noqa: BLE001 — Telegram down must not fail the tick
            pass
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EspAtlas Jr hourly tick (Phase 2 skeleton)")
    ap.add_argument("--dry-run", action="store_true", help="read-only: no worktree, no writes, no PR, no Telegram")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--max-calls", type=int, default=Budget().max_calls)
    ap.add_argument("--max-seconds", type=float, default=Budget().max_seconds)
    args = ap.parse_args(argv)
    r = run_tick(dry_run=args.dry_run, telegram=not args.no_telegram,
                 budget=Budget(max_calls=args.max_calls, max_seconds=args.max_seconds))
    return 1 if r.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
