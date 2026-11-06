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
   The research queue and the receipts join only as this run's own writes: each file is staged only
   while it still holds the exact bytes the miner or the broker wrote there. They land as a pair: when
   either half lost ownership (a foreign edit, one a broker CAS refused, one after a closure or one
   the broker found before any of its passes — the re-plan after a closure included), or
   the pair as it would land records a closure on one side only, neither is staged, the foreign
   bytes stay on disk and the work is reported not landed.
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
import demand_closure  # noqa: E402
import demand_signal  # noqa: E402
import publish  # noqa: E402
import pam_run  # noqa: E402
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
    pam: str = ""
    pam_receipt: dict = field(default_factory=dict)
    source_error: str = ""    # search failed, but independent PAM metadata may still have landed

    def line(self) -> str:
        return (self._head() + (f" · work {self.work}" if self.work else "")
                + (f" · {self.pam}" if self.pam else "")
                + (f" · search deferred: {self.source_error}" if self.source_error else ""))

    def _head(self) -> str:
        if self.aborted:
            return f"jr-demand: ABORTED — {self.aborted}"
        if self.published:
            merge = "auto-merge on" if self.auto_merge else f"auto-merge off ({self.reason})"
            return f"jr-demand: {self.date} landed {self.pr_url} · {merge}"
        return f"jr-demand: {self.date or '?'} not landed — {self.reason}"


class RunAbort(Exception):
    pass


class MiningUnavailable(RunAbort):
    """Search source failed/empty; independent source metadata can still be processed.

    Timeouts and other RunAbort signals are deliberately not this subtype.
    """


@dataclass
class Decision:
    snap: dict
    land: bool
    why: str
    research: str | None = None
    queue_only: bool = False      # zero demand items, a changed queue: land the queue alone
    queue_changed: bool = False
    receipts_changed: bool = False   # a reservation or settled receipt: docs/demand/work-receipts.json
    work_closed: bool = False        # the broker closed linked work in docs/demand/research-queue.json
    closed: list = field(default_factory=list)    # the work keys this run's broker closed
    pair_landed: bool = False        # only the queue/receipts pair (a queue change, the broker's writes) lands
    owned: dict = field(default_factory=dict)     # file name -> the exact bytes this run last wrote there
    base: dict | None = None         # file name -> main's bytes of the pair, before this run touched it
    foreign: set = field(default_factory=set)     # pair files another writer changed under this run
    bookkeeping: list = field(default_factory=list)   # the queue/receipts paths this publication stages
    withheld: str = ""               # why the queue/receipts pair is not staged
    work: str = ""                   # the broker's report line for that reservation
    pam_paths: tuple = ()
    pam_summary: str = ""
    pam_only: bool = False
    work_action: str = ""
    pam_ready: bool = False


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
        raise MiningUnavailable(f"miner failed (rc {getattr(p, 'returncode', '?')}): {err[:160]}")
    new = _read_latest(demand_dir)
    if new is None or not new.get("date") or _newest_stamp(demand_dir) == before:
        raise MiningUnavailable("miner wrote no snapshot")
    queue_after = _read_bytes(demand_dir / research_queue.QUEUE_NAME)
    owned = ({research_queue.QUEUE_NAME: queue_after}
             if queue_after is not None and queue_after != queue_before else {})   # the miner's own write
    queue_changed = _queue_comparable(queue_after) != _queue_comparable(queue_before)
    research = _queue_line(demand_dir, queue_before)
    if not new.get("items"):
        _restore_demand_files(demand_dir, files_before)      # an empty pull never replaces the snapshot
        if not queue_changed:
            raise MiningUnavailable("miner returned no demand items (Composio/GSC outage?) — not landing an empty steer")
        return Decision(new, True, "research queue changed; 0 demand items, snapshot not landed",
                        research, queue_only=True, queue_changed=True, owned=owned, pair_landed=True)
    land, why = should_land(new, prev, new["date"])    # age between the miner's own dates: one clock
    pair_landed = not land and queue_changed
    if pair_landed:
        land, why = True, f"research queue changed ({why})"
    return Decision(new, land, why, research, queue_changed=queue_changed, owned=owned, pair_landed=pair_landed)


PAIR = (research_queue.QUEUE_NAME, demand_broker.RECEIPTS_NAME)


def _note_foreign(d: Decision, demand_dir: Path) -> None:
    """Mark each pair file whose bytes are no longer what this run last left there (its own write,
    else main's): a broker pass over them builds on a foreign writer's bytes, so whatever it then
    writes is never this run's own."""
    if d.base is None:
        return
    d.foreign.update(n for n in PAIR if _read_bytes(demand_dir / n) != d.owned.get(n, d.base.get(n)))


def _bookkeeping(d: Decision, demand_dir: Path, base_queue: bytes | None,
                 base_receipts: bytes | None) -> tuple[list[str], str]:
    """(paths, why withheld) of the queue/receipts pair. A file joins only while it still holds the
    exact bytes this run wrote there (the miner's queue rewrite, the broker's durable writes); a later
    writer's bytes are never staged. The pair lands whole: when either half lost ownership, or the
    pair as it would land (main's bytes for a half not staged) records a closure on one side only,
    neither joins and both files are left on disk untouched. So does a pair a broker pass built over
    a foreign writer's bytes (`_note_foreign`)."""
    queue, receipts = PAIR
    names = [n for n in ((queue,) if d.work_closed or not d.pam_only else ()) + (receipts,) if n in d.owned]
    lost = [n for n in PAIR if n in d.foreign or (n in names and _read_bytes(demand_dir / n) != d.owned[n])]
    if lost:
        return [], f"{' and '.join(lost)} changed by another writer during this run"
    landing = {queue: base_queue, receipts: base_receipts, **{n: d.owned[n] for n in names}}
    keys = demand_broker.one_sided_closures(landing[queue], landing[receipts], base_receipts) if names else []
    if keys:
        return [], f"closure bookkeeping for work {', '.join(keys)} would land on one side only"
    return [f"{DEMAND_RELDIR}/{n}" for n in names], ""


def _withheld_line(d: Decision, work: str) -> str:
    """The work line once the pair is withheld: a closure that does not land is never reported closed."""
    head = (f"closure of {', '.join(d.closed)} not landed" if d.closed
            else " · ".join(filter(None, [work, "bookkeeping not landed"])))
    return (f"{head}: {d.withheld}; {research_queue.QUEUE_NAME} and {demand_broker.RECEIPTS_NAME} "
            "left on disk, not staged")


def _publication(d: Decision) -> tuple[list[str], str, str]:
    """(paths, subject, body) of the PR a landing decision opens."""
    snap = d.snap
    receipts = f"{DEMAND_RELDIR}/{demand_broker.RECEIPTS_NAME}"
    files = d.bookkeeping if d.work_closed else [p for p in d.bookkeeping if p == receipts]
    note = (f"\n\nWork {'closed' if d.work_closed else 'reserved'}: {d.work} in "
            + " and ".join(f"`{f}`" for f in files)
            + " (SPEC-demand-work-consumer.md) — bookkeeping only, no work PR." if files else "")
    if d.pam_paths:
        note += (f"\n\nPAM discovery: {d.pam_summary}. Unverified leads and source pointers only; "
                 "every publishable catalog fact still requires primary-source verification and review.")
    if d.pam_only:
        return (list(d.pam_paths) + d.bookkeeping, f"chore(jr): PAM discovery metadata {snap['date']}",
                "PAM discovery metadata only. The dated search-demand snapshot is not included; "
                "the prior committed steer is preserved. No catalog writes.\n\n"
                "Source: the two fixed public PAM feeds, through jr/pam_run.py and the existing "
                "daily runner. No new job or monitor." + note)
    if d.queue_only:
        return ([*d.bookkeeping, *d.pam_paths],
                f"chore(jr): research queue {snap['date']} — demand snapshot not landed (0 items)",
                _queue_only_body(snap, d.why, d.research) + note)
    paths = [f"{DEMAND_RELDIR}/{snap['date']}.json", f"{DEMAND_RELDIR}/{UNRESOLVED_NAME}", *d.bookkeeping]
    return (paths + list(d.pam_paths), f"chore(jr): demand snapshot {snap['date']} — {len(snap['items'])} item(s)",
            _pr_body(snap, d.why, d.research) + note)


def _note_work(d: Decision, work: demand_broker.Outcome) -> None:
    """Land what the broker's explicit result says it wrote; never inferred from file bytes, which a
    concurrent writer may have changed. A pair file the broker found changed by another writer is
    never this run's own again."""
    d.foreign.update(work.foreign)
    if work.closed:
        d.work_closed = True
        d.closed.append(work.closed)
    if work.changed:
        d.receipts_changed = d.receipts_changed or work.receipts_changed
        d.work = "; ".join(filter(None, [d.work, work.line()]))
        if not d.land:
            d.land, d.pair_landed = True, True
            d.why = f"work {'closed' if work.closed else 'reserved'} ({d.why})"


def _reserve_work(wt_path: Path, d: Decision, gh, now: datetime, repo_slug: str | None,
                  *, new_pam: bool = False, git=None, mined_revision: str | None = None,
                  close: bool = True, fetch=None) -> str:
    """Bookkeeping after a SUCCESSFUL mine: at most one work reservation, after closing linked work
    the broker verified against this run's snapshot mined at `mined_revision`. A broker failure is
    reported on the run line, never allowed to block the demand snapshot itself; a closure the
    broker reported durable before it raised still lands."""
    today = now.astimezone(timezone.utc).date().isoformat()
    closures: list = []
    _note_foreign(d, wt_path / DEMAND_RELDIR)          # before the broker reads the pair
    expected = None if d.base is None else {n: d.owned.get(n, d.base.get(n)) for n in PAIR}
    try:
        work = demand_broker.reserve(wt_path / DEMAND_RELDIR, d.snap, gh=gh, today=today,
                                     repo_slug=repo_slug, new_pam=new_pam, git=git,
                                     mined_revision=mined_revision, now=now, close=close, closures=closures,
                                     fetch=fetch,       # catalog_search: the live public search getter
                                     writes=d.owned,    # the exact bytes of each durable broker write
                                     expected=expected)     # ownership history, checked before every pass
    except RunAbort:
        raise                           # host timeout is fatal, not an ordinary source failure
    except Exception as e:  # noqa: BLE001
        for closed in closures:
            _note_work(d, closed)
        return f"defer: broker error {type(e).__name__}: {e}"
    d.work_action = work.action
    _note_work(d, work)
    return work.line()


def _inconsistent_landing(demand_dir: Path, d: Decision, receipts_before: bytes | None) -> str:
    """Why this run must not publish: its queue holds a candidate closed by a closure beside a receipt,
    as it would land, still live for that work (the receipts write and the restore both failed), or "".
    The worktree queue is checked even when a PAM-only publication would not stage it: refusing errs safe."""
    receipts = _read_bytes(demand_dir / demand_broker.RECEIPTS_NAME) if d.receipts_changed else receipts_before
    keys = demand_broker.inconsistent_closures(_read_bytes(demand_dir / research_queue.QUEUE_NAME), receipts)
    return (f"inconsistent closure bookkeeping for work {', '.join(keys)} (queue closed, receipt still live): "
            "not published" if keys else "")


def _refresh_pam(wt_path: Path, d: Decision, res: RunResult, refresh, now: datetime) -> None:
    """A deferred secondary source never prevents publishing successful search demand."""
    if refresh is None:
        return
    try:
        result = refresh(wt_path, now=now)
        paths = tuple(result.changed_paths)
        if (result.status not in {"updated", "unchanged", "deferred"}
                or (result.status == "updated" and paths != (pam_run.STATE_PATH,))
                or (result.status != "updated" and paths)
                or (paths and not (wt_path / pam_run.STATE_PATH).is_file())):
            res.pam = "PAM deferred: invalid changed-path manifest"
            return
        res.pam_receipt = result.report()
        d.pam_ready = result.status in ("updated", "unchanged")
        res.pam = (f"PAM {result.status}: {result.leads} leads / {result.potential_gaps} potential gaps"
                   + (f"; {result.error}" if result.error else ""))
        if paths:
            d.pam_paths = paths
            d.pam_summary = f"{result.leads} unverified leads / {result.potential_gaps} potential gaps"
            if not d.land:
                d.land, d.pam_only = True, True
                d.why = f"PAM metadata changed ({d.why})"
    except RunAbort:
        raise                           # a timeout must stop every source, not become a deferral
    except Exception as exc:  # noqa: BLE001 — secondary-source failure is independently reported
        res.pam = f"PAM deferred: {type(exc).__name__}"


def run(*, git=publish.default_git, gh=publish.default_gh, miner=default_miner,
        python: str = DEFAULT_DEMAND_PYTHON, telegram: bool = False, now: datetime | None = None,
        root: Path | None = None, repo_slug: str | None = None, auto_merge: bool = True,
        pam_refresh=None, fetch=demand_closure.default_fetch) -> RunResult:
    now = now or datetime.now(timezone.utc)
    res = RunResult()
    wt = branch = None
    try:
        wt = publish.add_worktree(git=git, root=root)
        if not publish.is_clean(wt, git=git):
            raise RunAbort("fresh worktree is not clean")
        demand_dir = wt.path / DEMAND_RELDIR
        files_before = _demand_files(demand_dir) if pam_refresh is not None else None
        queue_before = _read_bytes(demand_dir / research_queue.QUEUE_NAME)        # main's bookkeeping pair
        main_receipts = _read_bytes(demand_dir / demand_broker.RECEIPTS_NAME)
        try:
            decision = _mine_and_decide(wt, miner, python, telegram)
        except MiningUnavailable as exc:
            if pam_refresh is None:
                raise
            # A failed miner may leave partial JSON. Restore its snapshot/queue
            # writes before considering a publication from the independent feed.
            _restore_demand_files(demand_dir, files_before)
            queue_path = demand_dir / research_queue.QUEUE_NAME
            if queue_before is None:
                queue_path.unlink(missing_ok=True)
            else:
                queue_path.write_bytes(queue_before)
            res.source_error = str(exc)
            decision = Decision({"date": now.astimezone(timezone.utc).date().isoformat(), "items": []},
                                False, "search refresh unavailable", pam_only=True)
        res.date = decision.snap["date"]
        decision.base = {research_queue.QUEUE_NAME: queue_before, demand_broker.RECEIPTS_NAME: main_receipts}
        closer = {"git": git, "mined_revision": wt.base_sha,      # the catalog revision this run mined
                  "fetch": fetch}                                # the live getter catalog_search reads through
        receipts_before = _read_bytes(demand_dir / demand_broker.RECEIPTS_NAME)
        if not res.source_error:
            res.work = _reserve_work(wt.path, decision, gh, now, repo_slug, **closer)
        _refresh_pam(wt.path, decision, res, pam_refresh, now)
        # The first pass already recovers existing PAM branches/PRs from valid
        # cached provenance. Only a prior NOOP or a closure permits starting new feed
        # work. Existing work, caps, unreadable remote state and timeouts retain priority.
        if (not res.source_error and decision.pam_ready
                and (decision.work_action == "noop" or decision.work_closed)):
            second = _reserve_work(wt.path, decision, gh, now, repo_slug, new_pam=True,
                                   close=not decision.work_closed, **closer)   # one closure per run
            res.work = f"{res.work} · then {second}" if decision.work_closed else second
        if res.pam_receipt:
            revision = git("rev-parse", "HEAD")
            res.pam_receipt["runner_revision"] = ((getattr(revision, "stdout", "") or "").strip()
                                                  if getattr(revision, "returncode", 1) == 0 else "unknown")
            res.pam_receipt["catalog_revision"] = wt.base_sha
        if not decision.land:
            res.reason = decision.why
            if res.source_error:
                res.aborted = res.source_error
            return res
        inconsistent = _inconsistent_landing(demand_dir, decision, receipts_before)
        if inconsistent:
            if decision.closed:                 # a closure that never lands is never reported closed
                decision.withheld = "the pair is inconsistent"
                res.work = _withheld_line(decision, res.work)
            raise RunAbort(inconsistent)        # never land a closed queue beside its live receipt
        decision.bookkeeping, decision.withheld = _bookkeeping(decision, demand_dir, queue_before, main_receipts)
        if decision.withheld:
            res.work = _withheld_line(decision, res.work)
            decision.research = None                            # the queue's digest no longer lands
            if decision.pair_landed:                            # the withheld pair was the reason to land
                if not decision.pam_paths:
                    raise RunAbort(f"bookkeeping not landed: {decision.withheld}; nothing else to publish")
                decision.pam_only, decision.queue_only = True, False
                decision.why = f"PAM metadata changed; bookkeeping not landed: {decision.withheld}"
        prefix = QUEUE_ONLY_PREFIX if decision.queue_only or decision.pam_only else BRANCH_PREFIX
        branch = f"{prefix}{now.strftime('%Y%m%d-%H%M')}"
        paths, subject, body = _publication(decision)
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
            telegram=args.telegram, auto_merge=not args.no_auto_merge,
            pam_refresh=pam_run.refresh_worktree)
    print(r.line())
    if r.pam_receipt:
        print("PAM receipt: " + json.dumps(r.pam_receipt, sort_keys=True))
    return 1 if r.aborted or r.source_error else 0


if __name__ == "__main__":
    sys.exit(main())
