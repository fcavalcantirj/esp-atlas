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
  5. Allocation — the hourly path splits HOURLY_TRACK_UNITS gauge-driven units between
     Track A (admit) and Track B (board-map) via jr/allocator.py (boards < 50%: B-heavy;
     50–80%: even; above 80%: A-heavy — bands provisional, Felipe gates them); --track
     keeps the manual text as the override.
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
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import ledger   # noqa: E402
import memory   # noqa: E402
import publish  # noqa: E402
import report   # noqa: E402
import allocator  # noqa: E402
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
STAGES: list = []   # extra stages appended by hand; the hourly content stages come from hourly_stages()


def hourly_stages(split: dict) -> list:
    """The content stages of the HOURLY path, from the allocator's split (Phase 6 cutover):
    Track B (jr/stage_boardmap: map a firmware's boards as cited recipes) with `B` firmware,
    Track A (jr/stage_admit: score launcher candidates, write admitted records) with `A`
    candidates. The heavier track runs first so the call budget goes where the gauge says."""
    out = []
    a, b = int(split.get("A") or 0), int(split.get("B") or 0)
    if b:
        import stage_boardmap
        out.append(("boardmap", b, lambda ctx, n=b: stage_boardmap.run(ctx, budget=n)))
    if a:
        import stage_admit
        out.append(("admit", a, lambda ctx, n=a: stage_admit.run(ctx, budget=n)))
    out.sort(key=lambda s: -s[1])
    return [fn for _, _, fn in out]


# --- defaults for the injectable effects -------------------------------------------------------

def default_gauge(data_dir: Path) -> dict:
    sys.path.insert(0, str(REPO / "scripts"))
    import data_completion  # noqa: E402
    return data_completion.compute_completion(str(data_dir))


def guard_env(root: Path, base: dict | None = None) -> dict:
    """The environment that makes esp_atlas_core look at the WORKTREE. Without it the editable
    install resolves `esp_atlas_core` to the clone's checkout and `paths.py` to the clone's
    data/, so the guard would validate the wrong tree while claiming to test this one."""
    env = dict(os.environ if base is None else base)
    env["ESP_ATLAS_REPO_ROOT"] = str(root)
    src = str(root / "apps" / "core" / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def default_guard(root: Path) -> dict:
    """validate.py against the worktree's code AND data (see guard_env), never the clone's.

    The three CI regression files (coverage matrix, examples, intent oracle) run here only when
    JR_GUARD_TESTS=1: measured at 167 s of CPU on a laptop (examples alone 97 s), which on the
    Pi means minutes at full load every hour the tick writes, on a box that runs at its thermal
    warn line — and CI runs the same files as required checks before anything can merge, so a
    red PR simply does not merge. Belt-and-braces stays available, off by default."""
    env = guard_env(root)
    v = subprocess.run([sys.executable, "scripts/validate.py"], cwd=root, capture_output=True,
                       text=True, timeout=300, env=env)
    if v.returncode != 0:
        return {"ok": False, "output": (v.stdout + v.stderr).strip()[-2000:]}
    if os.environ.get("JR_GUARD_TESTS", "0") != "1":
        return {"ok": True, "output": (v.stdout + v.stderr).strip()[-2000:] + "\n(guard tests skipped: JR_GUARD_TESTS!=1; CI runs them)"}
    t = subprocess.run([sys.executable, "-m", "pytest", "apps/core/tests/test_coverage_matrix.py",
                        "apps/core/tests/test_examples.py", "apps/core/tests/test_intent_oracle.py", "-q"],
                       cwd=root, capture_output=True, text=True, timeout=600, env=env)
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
    """A Jr tick PR open longer than `hours`, or the sentinel "unknown" when the query itself
    fails — fail CLOSED, like the rate-limit probe: a tick that cannot see its own PRs must not
    open another."""
    p = gh("pr", "list", "--state", "open", "--json", "number,createdAt,headRefName")
    if getattr(p, "returncode", 1) != 0:
        return "unknown"
    try:
        prs = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return "unknown"
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
             stale_pr_hours: float = STALE_PR_HOURS, telegram: bool = True,
             auto_merge: bool = True) -> report.TickReport:
    now = now or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    budget = budget or Budget()
    gh_c = budget.wrap(gh)
    r = report.TickReport(when=now, dry_run=dry_run)
    hourly = stages is None   # the hourly path: gauge-driven split; --track overrides it
    stages = STAGES if hourly else stages
    wt = None
    try:
        # 1. preflight
        remaining = _rate_limit_remaining(gh_c)
        if remaining is None:
            raise TickAbort("gh unavailable (rate_limit query failed)")
        if remaining < min_rate_limit:
            raise TickAbort(f"GitHub rate limit low: {remaining} < {min_rate_limit}")
        stale = _stale_tick_pr(gh_c, now, stale_pr_hours)
        if stale == "unknown":
            raise TickAbort("gh pr list failed (cannot see open Jr PRs)")
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
            root, ledger_path = REPO, ledger.DEFAULT_LEDGER_PATH
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
            # A PR that merged between our fetch of origin/main and the `gh pr view` above is
            # catalogued on GitHub but not yet in this worktree: treat what reconcile_prs just
            # settled as catalogued, or it would be rejected as "removed from catalog".
            removed = memory.reconcile_removed(catalogued | set(settled["merged"]), path=ledger_path, now=now)
            r.memory = {"expired": len(expired), "merged": len(settled["merged"]) + len(merged),
                        "rejected": len(settled["rejected"]), "removed": len(removed)}
            if settled["merged"] or merged or removed:
                r.revalidate = revalidate(env.get("REVALIDATE_SECRET"))

        # 4. gauge
        g = gauge(root / "data")
        r.boards_pct = float(g.get("entities", {}).get("boards", {}).get("pct", 0.0))
        r.overall_pct = float(g.get("overall_pct", 0.0))

        # 5. allocation — hourly: the gauge-driven A/B split; manual (--track): the override text
        if hourly:
            split = allocator.allocate(r.boards_pct, allocator.HOURLY_TRACK_UNITS)
            r.allocation = (f"boards {r.boards_pct:.1f}% -> "
                            f"A{split['A']}/B{split['B']} (hourly)")
            stages = list(stages) + hourly_stages(split)
        else:
            n = len(stages)
            r.allocation = (f"boards {r.boards_pct:.1f}% -> A0/B{n} (manual track)" if n
                            else f"boards {r.boards_pct:.1f}% -> A0/B0 (no content stages registered)")

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

        # 7. guard once (data writes only), 8. publish — when a stage wrote OR memory changed;
        #    a ledger-only tick still ships, or every reconciliation would die with the worktree.
        ledger_changed = any(r.memory.values()) if r.memory else False
        if (r.paths or ledger_changed) and not dry_run:
            if r.paths:
                r.guard = guard(root)
                if not r.guard.get("ok"):
                    raise TickAbort("guard red — worktree discarded, nothing published")
                subject = f"feat(jr): tick {now.strftime('%Y-%m-%d %H:%M')} UTC — {len(r.paths)} path(s)"
            else:
                subject = f"chore(jr): tick {now.strftime('%Y-%m-%d %H:%M')} UTC — memory reconciliation"
            # publish gets the UNCOUNTED gh: its two calls (pr create, pr merge) must never be cut
            # off by the budget after the push has already happened.
            res = publish.publish(wt, r.paths, subject, report.render_pr_body(r), git=git, gh=gh,
                                  now=now, repo_slug=slug, needs_human=r.needs_human,
                                  protection=protection, auto_merge=auto_merge)
            r.publish = res.as_dict()
    except BudgetExceeded as e:
        r.aborted = f"budget: {e}"
    except TickAbort as e:
        r.aborted = str(e)
    except Exception as e:  # noqa: BLE001 — a tick must always end with a report line
        r.aborted = f"{type(e).__name__}: {e}"
    finally:
        if wt is not None:
            try:
                publish.remove_worktree(wt, git=git)
                if r.publish and r.publish.get("branch"):
                    publish.cleanup_branch(r.publish["branch"], git=git)
            except Exception as e:  # noqa: BLE001 — cleanup must never eat the report
                r.warnings.append(f"worktree cleanup failed: {type(e).__name__}: {e}")
        r.budget = budget.summary()

    line = report.render_line(r)
    print(line)
    if telegram and not dry_run and notifier is not None:
        try:
            notifier(line)
        except Exception:  # noqa: BLE001 — Telegram down must not fail the tick
            pass
    return r


def _on_sigterm(signum, frame):
    # scripts/jr-tick.sh wraps the tick in `timeout`, which sends SIGTERM. Python's default
    # disposition dies WITHOUT running `finally`, leaking the worktree and skipping the report.
    # Raising turns it into an ordinary abort: worktree removed, one line printed, exit 1.
    raise TickAbort("terminated by SIGTERM (timeout)")


def stages_for(track: str | None, budget_units: int, only: list[str] | None = None) -> list | None:
    """The stage list for a CLI run. None → the registered STAGES (empty until the Phase 6
    cutover). Track B (PLAN §4 Phase 4, driven by hand until the cutover:
    `--track B --budget 3`) maps the most under-mapped firmware's boards as cited recipes.
    Track A (Phase 3, driven by hand until the cutover: `--track A --budget N`) admits new
    firmware from the launcher catalog as cited records."""
    if track is None:
        return None
    if track.upper() == "B":
        import stage_boardmap
        return [lambda ctx: stage_boardmap.run(ctx, budget=budget_units, only=only)]
    if track.upper() == "A":
        import stage_admit
        return [lambda ctx: stage_admit.run(ctx, budget=budget_units)]
    raise SystemExit(f"unknown track {track!r} (tracks A and B)")


def main(argv=None) -> int:
    signal.signal(signal.SIGTERM, _on_sigterm)
    ap = argparse.ArgumentParser(description="EspAtlas Jr hourly tick")
    ap.add_argument("--dry-run", action="store_true", help="read-only: no worktree, no writes, no PR, no Telegram")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--max-calls", type=int, default=Budget().max_calls)
    ap.add_argument("--max-seconds", type=float, default=Budget().max_seconds)
    ap.add_argument("--track", choices=["A", "B", "a", "b"], default=None, help="run ONE content track by hand (B = map boards as recipes)")
    ap.add_argument("--budget", type=int, default=3, help="units for --track (B: firmware per run)")
    ap.add_argument("--firmware", default=None,
                    help="--track B only: comma-separated firmware ids to map, in this order, ignoring freshness (manual override of the selector)")
    ap.add_argument("--no-auto-merge", action="store_true",
                    help="open the PR but never request auto-merge (a human merges) — the manual-track default until the cutover")
    args = ap.parse_args(argv)
    only = [f.strip() for f in args.firmware.split(",") if f.strip()] if args.firmware else None
    if only and (args.track or "").upper() != "B":
        ap.error("--firmware needs --track B")
    r = run_tick(dry_run=args.dry_run, telegram=not args.no_telegram,
                 budget=Budget(max_calls=args.max_calls, max_seconds=args.max_seconds),
                 stages=stages_for(args.track, args.budget, only), auto_merge=not args.no_auto_merge)
    return 1 if r.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
