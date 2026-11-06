"""EspAtlas Jr — the daily demand runner (jr/demand_run.py; cron entrypoint scripts/jr-demand.sh).

F2 (2026-11-03): the read-only miner (jr/demand.py) was never scheduled, so the newest committed
snapshot aged past the steer's 14-day window and every tick printed "demand snapshot stale — not
steering". The tick cannot mine itself (the miner needs the composio venv), so this runner does
it once a day and lands the snapshot through the tick's own PR path (jr/publish.py):

1. a fresh worktree detached at origin/main (publish.add_worktree) — the clone is never touched;
2. the worktree's OWN jr/demand.py, run with the composio interpreter (JR_DEMAND_PYTHON), so the
   miner reads main's catalog and writes `docs/demand/<date>.json` + `docs/demand/unresolved.json`
   inside the worktree. Its Telegram digest is opt-in (`--telegram`), off by default;
3. no-op when the new snapshot equals the previous one apart from its date fields — unless the
   previous one is REFRESH_DAYS old, so steady demand never reads as stale to the tick;
   A changed research queue (`docs/demand/research-queue.json`, SPEC-demand-research-queue.md)
   lands even when the snapshot is a no-op;
   with zero demand items it lands ALONE (a queue-only PR on `jr/demand-queue-…`): every other
   docs/demand file the miner touched is restored, so the dated snapshot is never replaced;
4. otherwise publish.publish() with exactly those paths (bookkeeping only, no catalog write)
   on a `jr/demand-…` branch — outside the tick's `jr/tick-*` triage — with the same protection
   and earned-trust auto-merge gate as a tick. Only an older proven snapshot-only demand PR
   is closed as superseded; queue-bearing or unreadable PRs wait for review.
5. after mining, jr/demand_broker.py reserves at most ONE demand work item
   (SPEC-demand-work-consumer.md) in `docs/demand/work-receipts.json`, which joins the
   publication only when it changed — and a new reservation lands even on a no-op demand day.

An empty pull (zero items) is refused as a steer: it is a Composio/GSC outage far more often than
zero demand, and landing it would erase the steer — only a changed research queue may land then. `git`, `gh` and the miner are injectable; tests use fakes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand_broker  # noqa: E402
import demand_signal  # noqa: E402
import publish  # noqa: E402
import research_queue  # noqa: E402
import review_routing  # noqa: E402
from tick import guard_env  # noqa: E402 — the one "esp_atlas_core sees the worktree" env

DEFAULT_DEMAND_PYTHON = "/home/browbot/.composio-venv/bin/python"
DEMAND_RELDIR = "docs/demand"
UNRESOLVED_NAME = "unresolved.json"
BRANCH_PREFIX = "jr/demand-"
QUEUE_ONLY_PREFIX = "jr/demand-queue-"   # queue-bearing PRs are never automatically superseded
REFRESH_DAYS = 7          # half the loader's 14-day stale window: an unchanged snapshot still lands weekly
DATE_FIELDS = ("date", "window")
ITEM_DATE_FIELDS = ("first_seen", "last_seen")
SUPERSEDED_COMMENT = ("Superseded by a newer daily demand snapshot. The complete changed-file "
                      "manifest contains only dated demand snapshots and/or unresolved.json, "
                      "not the research queue. Closed automatically by jr/demand_run.py.")


@dataclass
class RunResult:
    published: bool = False
    date: str = ""
    pr_url: str = ""
    auto_merge: bool = False
    reason: str = ""
    aborted: str = ""
    superseded: list = field(default_factory=list)
    work: str = ""            # the demand work broker's decision (jr/demand_broker.py)

    def line(self) -> str:
        return self._head() + (f" · work {self.work}" if self.work else "")

    def _head(self) -> str:
        if self.aborted:
            return f"jr-demand: ABORTED — {self.aborted}"
        if self.published:
            merge = "auto-merge on" if self.auto_merge else f"auto-merge off ({self.reason})"
            return f"jr-demand: {self.date} landed {self.pr_url} · {merge}"
        return f"jr-demand: {self.date or '?'} not landed — {self.reason}"


class RunAbort(Exception):
    pass


@dataclass
class Decision:
    snap: dict
    land: bool
    why: str
    research: str | None = None
    queue_only: bool = False      # zero demand items, a changed queue: land the queue alone
    queue_changed: bool = False
    receipts_changed: bool = False   # a new work reservation: docs/demand/work-receipts.json
    work: str = ""                   # the broker's report line for that reservation


# --- the no-op rule ----------------------------------------------------------------------------------

def comparable(snapshot: dict) -> dict:
    """The snapshot minus every field that moves just because a day passed."""
    out = {k: v for k, v in snapshot.items() if k not in DATE_FIELDS}
    out["items"] = [{k: v for k, v in it.items() if k not in ITEM_DATE_FIELDS}
                    for it in snapshot.get("items") or []]
    return out


def is_noop(new: dict, prev: dict | None) -> bool:
    return prev is not None and comparable(new) == comparable(prev)


def should_land(new: dict, prev: dict | None, today_str: str,
                refresh_days: int = REFRESH_DAYS) -> tuple[bool, str]:
    if not is_noop(new, prev):
        return True, "demand changed" if prev else "first snapshot"
    try:
        age = (dt.date.fromisoformat(today_str) - dt.date.fromisoformat(prev["date"])).days
    except (KeyError, TypeError, ValueError):
        age = None
    if age is None or age >= refresh_days:
        return True, f"refresh: unchanged, but {prev.get('date')} is {age} d old"
    return False, f"no-op: demand unchanged since {prev['date']}"


# --- snapshot files ----------------------------------------------------------------------------------

def _dated_snapshots(demand_dir: Path) -> list[Path]:
    return sorted(p for p in demand_dir.glob("*.json") if demand_signal.is_dated_snapshot(p))


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _queue_comparable(raw: bytes | None):
    """The queue minus each candidate's `last_seen`, `window` and `evidence.checked`: an open
    candidate is re-sighted (over a window one day later) every day the 28-day window holds it,
    and the catalog grows hourly — neither alone
    may open a PR (the weekly refresh carries them)."""
    try:
        queue = json.loads(raw) if raw else research_queue.empty_queue()   # absent == empty
    except (ValueError, UnicodeDecodeError):
        return raw
    if not isinstance(queue, dict) or not isinstance(queue.get("candidates"), dict):
        return queue
    return {**queue, "candidates": {k: _candidate_comparable(c) for k, c in queue["candidates"].items()}}


QUEUE_MOVING_FIELDS = ("last_seen", "window")   # move every day the 28-day window still holds a term


def _candidate_comparable(c):
    if not isinstance(c, dict):
        return c
    out = {f: v for f, v in c.items() if f not in QUEUE_MOVING_FIELDS}
    if isinstance(out.get("evidence"), dict):
        out["evidence"] = {f: v for f, v in out["evidence"].items() if f != "checked"}
    return out


def _queue_line(demand_dir: Path, before: bytes | None) -> str | None:
    """The research-queue line for the PR body: candidates added by this run + what is open."""
    path = demand_dir / research_queue.QUEUE_NAME
    if not path.exists():
        return None
    try:
        queue = research_queue.load_queue(path)
        prev = json.loads(before).get("candidates", {}) if before else {}
    except (ValueError, AttributeError):
        return None
    opened = [k for k in queue["candidates"] if k not in prev]
    reopened = [k for k, c in queue["candidates"].items() if isinstance(prev.get(k), dict)
                and prev[k].get("status") == research_queue.STATUS_CLOSED
                and c.get("status") != research_queue.STATUS_CLOSED]
    return research_queue.digest_line(queue, {"opened": opened, "reopened": reopened})


def _demand_files(demand_dir: Path) -> dict[str, bytes]:
    """Every docs/demand file but the research queue, by name — what a queue-only run restores."""
    if not demand_dir.is_dir():
        return {}
    return {p.name: p.read_bytes() for p in demand_dir.iterdir()
            if p.is_file() and p.name != research_queue.QUEUE_NAME}


def _restore_demand_files(demand_dir: Path, before: dict[str, bytes]) -> None:
    """Undo the miner's snapshot writes: drop files it added, put back the bytes it changed."""
    for name, data in _demand_files(demand_dir).items():
        if name not in before:
            (demand_dir / name).unlink()
        elif data != before[name]:
            (demand_dir / name).write_bytes(before[name])
    for name, data in before.items():
        if not (demand_dir / name).exists():
            (demand_dir / name).write_bytes(data)


def _read_latest(demand_dir: Path) -> dict | None:
    files = _dated_snapshots(demand_dir)
    if not files:
        return None
    try:
        snap = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return snap if isinstance(snap, dict) else None


# --- the miner ---------------------------------------------------------------------------------------

def default_miner(wt_path: Path, *, python: str, telegram: bool) -> subprocess.CompletedProcess:
    """The worktree's own jr/demand.py under the composio interpreter: main's code, main's catalog.
    `guard_env` points esp_atlas_core (imported by jr/tools.py, not installed in the composio
    venv) at the worktree's apps/core/src and data, exactly as the tick's guard does."""
    argv = [python, "jr/demand.py", *(["--telegram"] if telegram else [])]
    return subprocess.run(argv, cwd=wt_path, capture_output=True, text=True, env=guard_env(wt_path))


def _pr_body(snap: dict, why: str, research: str | None = None) -> str:
    items = snap.get("items") or []
    align = demand_signal.alignment(snap, None, top_n=5)
    bias = demand_signal.steer_signal(snap)["bias"]
    lines = [f"Daily demand snapshot `{DEMAND_RELDIR}/{snap.get('date')}.json` "
             f"(window {snap.get('window', {}).get('start')}→{snap.get('window', {}).get('end')}) — {why}.",
             "",
             f"- {len(items)} items · " + " · ".join(f"{k} {v}" for k, v in align["counts"].items()),
             f"- steer bias {bias:+.4f} · aligned {align['aligned_pct']}%",
             "",
             "Top demanded-but-missing:"]
    lines += [f"- `{m['term']}` — {m['gap']}, w={m['weight']}" for m in align["demanded_but_missing"]] or ["- none"]
    if research:
        lines += ["", research, "(zero-result searches to research — never catalog content; "
                  "SPEC-demand-research-queue.md)"]
    lines += ["", "Bookkeeping only (docs/demand/**), no catalog writes. Read-only miner: jr/demand.py; "
              "runner: jr/demand_run.py (F2)."]
    return "\n".join(lines)


def _queue_only_body(snap: dict, why: str, research: str | None) -> str:
    window = snap.get("window") or {}
    return "\n".join([
        f"Research queue `{DEMAND_RELDIR}/{research_queue.QUEUE_NAME}` only — {why}.", "",
        research or "🔬 research queue changed",
        "(zero-result searches to research — never catalog content; SPEC-demand-research-queue.md)", "",
        f"The miner returned 0 demand items for window {window.get('start')}→{window.get('end')}, so the "
        f"dated snapshot `{DEMAND_RELDIR}/{snap.get('date')}.json` is not landed (an empty pull is an "
        "outage far more often than zero demand); the steer keeps main's latest snapshot.", "",
        f"Bookkeeping only ({DEMAND_RELDIR}/{research_queue.QUEUE_NAME}), no catalog writes. "
        "Runner: jr/demand_run.py."])


def _snapshot_only(pr: dict) -> bool:
    """Closing needs positive evidence: incomplete file lists can hide queue changes."""
    files, count = pr.get("files"), pr.get("changedFiles")
    if not isinstance(files, list) or type(count) is not int or count <= 0 or len(files) != count:
        return False
    for entry in files:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or Path(path).parent != Path(DEMAND_RELDIR):
            return False
        # A renamed queue can have a snapshot-looking new path; without the
        # original path this manifest cannot prove it was only a snapshot.
        if entry.get("changeType") not in {"ADDED", "MODIFIED", "DELETED"}:
            return False
        if Path(path).name != UNRESOLVED_NAME and not demand_signal.is_dated_snapshot(Path(path)):
            return False
    return True


def _close_superseded(gh, keep_branch: str, prefix: str = BRANCH_PREFIX) -> list[int]:
    p = gh("pr", "list", "--state", "open", "--limit", "500", "--json", "number,headRefName,labels,files,changedFiles")
    try:
        prs = json.loads(getattr(p, "stdout", "") or "[]") if getattr(p, "returncode", 1) == 0 else []
    except json.JSONDecodeError:
        prs = []
    closed = []
    for pr in prs:
        head = str(pr.get("headRefName", "")) if isinstance(pr, dict) else ""
        # Every run starts from main, not the previous PR. Never discard an unmerged
        # queue or its human lifecycle data merely because a new queue was generated.
        if (head.startswith(prefix) and not head.startswith(QUEUE_ONLY_PREFIX) and head != keep_branch
                and not review_routing.has_review_label(pr) and _snapshot_only(pr)):
            r = gh("pr", "close", str(pr.get("number")), "--comment", SUPERSEDED_COMMENT, "--delete-branch")
            if getattr(r, "returncode", 1) == 0:
                closed.append(pr.get("number"))
    return closed


# --- the run -----------------------------------------------------------------------------------------

def _newest_stamp(demand_dir: Path) -> tuple | None:
    """(name, mtime_ns) of the newest dated snapshot: any (re)write by the miner changes it, even a
    same-day rewrite with identical content; main's untouched checkout never does."""
    files = _dated_snapshots(demand_dir)
    return (files[-1].name, files[-1].stat().st_mtime_ns) if files else None


def _mine_and_decide(wt: publish.Worktree, miner, python: str, telegram: bool) -> Decision:
    demand_dir = wt.path / DEMAND_RELDIR
    prev = _read_latest(demand_dir)          # read BEFORE the miner may overwrite a same-day file
    before = _newest_stamp(demand_dir)
    files_before = _demand_files(demand_dir)
    queue_before = _read_bytes(demand_dir / research_queue.QUEUE_NAME)
    p = miner(wt.path, python=python, telegram=telegram)
    if getattr(p, "returncode", 1) != 0:
        err = ((getattr(p, "stderr", "") or "").strip().splitlines() or [""])[-1]
        raise RunAbort(f"miner failed (rc {getattr(p, 'returncode', '?')}): {err[:160]}")
    new = _read_latest(demand_dir)
    if new is None or not new.get("date") or _newest_stamp(demand_dir) == before:
        raise RunAbort("miner wrote no snapshot")
    queue_changed = (_queue_comparable(_read_bytes(demand_dir / research_queue.QUEUE_NAME))
                     != _queue_comparable(queue_before))
    research = _queue_line(demand_dir, queue_before)
    if not new.get("items"):
        _restore_demand_files(demand_dir, files_before)      # an empty pull never replaces the snapshot
        if not queue_changed:
            raise RunAbort("miner returned no demand items (Composio/GSC outage?) — not landing an empty steer")
        return Decision(new, True, "research queue changed; 0 demand items, snapshot not landed",
                        research, queue_only=True, queue_changed=True)
    land, why = should_land(new, prev, new["date"])    # age between the miner's own dates: one clock
    if not land and queue_changed:
        land, why = True, f"research queue changed ({why})"
    return Decision(new, land, why, research, queue_changed=queue_changed)


def _publication(d: Decision, wt_path: Path) -> tuple[list[str], str, str]:
    """(paths, subject, body) of the PR a landing decision opens."""
    snap, queue_path = d.snap, f"{DEMAND_RELDIR}/{research_queue.QUEUE_NAME}"
    receipts = [f"{DEMAND_RELDIR}/{demand_broker.RECEIPTS_NAME}"] if d.receipts_changed else []
    note = (f"\n\nWork reserved: {d.work} in `{receipts[0]}` (SPEC-demand-work-consumer.md) — "
            "bookkeeping only, no work PR." if receipts else "")
    if d.queue_only:
        return ([queue_path, *receipts],
                f"chore(jr): research queue {snap['date']} — demand snapshot not landed (0 items)",
                _queue_only_body(snap, d.why, d.research) + note)
    paths = [f"{DEMAND_RELDIR}/{snap['date']}.json", f"{DEMAND_RELDIR}/{UNRESOLVED_NAME}"]
    if (wt_path / queue_path).exists():
        paths.append(queue_path)
    return (paths + receipts, f"chore(jr): demand snapshot {snap['date']} — {len(snap['items'])} item(s)",
            _pr_body(snap, d.why, d.research) + note)


def _reserve_work(wt_path: Path, d: Decision, gh, now: datetime, repo_slug: str | None) -> str:
    """Bookkeeping after mining: at most one work reservation. A broker failure is reported on
    the run line, never allowed to block the demand snapshot itself."""
    today = now.astimezone(timezone.utc).date().isoformat()
    try:
        work = demand_broker.reserve(wt_path / DEMAND_RELDIR, d.snap, gh=gh, today=today, repo_slug=repo_slug)
    except Exception as e:  # noqa: BLE001
        return f"defer: broker error {type(e).__name__}: {e}"
    if work.changed:
        d.receipts_changed, d.work = True, work.line()
        if not d.land:
            d.land, d.why = True, f"work reserved ({d.why})"
    return work.line()


def run(*, git=publish.default_git, gh=publish.default_gh, miner=default_miner,
        python: str = DEFAULT_DEMAND_PYTHON, telegram: bool = False, now: datetime | None = None,
        root: Path | None = None, repo_slug: str | None = None, auto_merge: bool = True) -> RunResult:
    now = now or datetime.now(timezone.utc)
    res = RunResult()
    wt = branch = None
    try:
        wt = publish.add_worktree(git=git, root=root)
        if not publish.is_clean(wt, git=git):
            raise RunAbort("fresh worktree is not clean")
        decision = _mine_and_decide(wt, miner, python, telegram)
        res.date = decision.snap["date"]
        res.work = _reserve_work(wt.path, decision, gh, now, repo_slug)
        if not decision.land:
            res.reason = decision.why
            return res
        prefix = QUEUE_ONLY_PREFIX if decision.queue_only else BRANCH_PREFIX
        branch = f"{prefix}{now.strftime('%Y%m%d-%H%M')}"
        paths, subject, body = _publication(decision, wt.path)
        pub = publish.publish(wt, paths, subject, body, git=git, gh=gh, now=now,
                              repo_slug=repo_slug, auto_merge=auto_merge, branch=branch)
        res.published, res.pr_url, res.auto_merge = pub.published, pub.pr_url, pub.auto_merge
        res.reason = pub.reason or decision.why
        if not pub.published:
            raise RunAbort(f"publish failed: {pub.reason}")    # never exit 0 like a no-op
        res.superseded = _close_superseded(gh, branch, prefix)
    except RunAbort as e:
        res.aborted = str(e)
    except Exception as e:  # noqa: BLE001 — a run must always end with a report line
        res.aborted = f"{type(e).__name__}: {e}"
    finally:
        if wt is not None:
            try:
                publish.remove_worktree(wt, git=git)
                if branch:      # after the worktree is gone: git won't delete a checked-out branch
                    publish.cleanup_branch(branch, git=git)
            except Exception as e:  # noqa: BLE001
                res.reason = (res.reason + f" · worktree cleanup failed: {e}").strip(" ·")
    return res


def _on_sigterm(signum, frame):
    raise RunAbort("killed by timeout (SIGTERM)")


def main(argv=None) -> int:
    signal.signal(signal.SIGTERM, _on_sigterm)
    ap = argparse.ArgumentParser(description="EspAtlas Jr daily demand runner")
    ap.add_argument("--telegram", action="store_true", help="let the miner send its digest (off by default)")
    ap.add_argument("--no-auto-merge", action="store_true", help="open the PR but never request auto-merge")
    args = ap.parse_args(argv)
    r = run(python=os.environ.get("JR_DEMAND_PYTHON") or DEFAULT_DEMAND_PYTHON,
            telegram=args.telegram, auto_merge=not args.no_auto_merge)
    print(r.line())
    return 1 if r.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
