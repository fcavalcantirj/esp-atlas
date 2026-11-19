"""EspAtlas Jr — CI watch and self-heal hand-off (jr/ci_watch.py, SPEC-jr-self-heal.md).

Deterministic, no model. Every tick calls `watch()` from its preflight; it never raises, so a red or
unreadable CI never stops a tick. It reads the required checks from branch protection, the newest
`validate` run on main and the newest tick PRs, and decides:

  rerun      a required check was cancelled / timed out / failed to start on its first attempt
  incident   a required check failed on main, or two consecutive tick PRs fail with the same
             fingerprint (two different contents, one failure: the cause is outside both PRs)
  none       anything else (one red tick PR is its own content's problem; review routing has it)

An incident is written to a runner-local Store (outside the repo: the repo is public). The operator's
launcher takes it with `python3 jr/ci_watch.py claim` (at most two per UTC day), runs the coding
delegate on the incident's branch with docs/ops/HEAL-PROMPT.md, and runs
`python3 jr/ci_watch.py relay-check` before pushing. Nothing here merges anything.

    python3 jr/ci_watch.py claim [--state PATH]
    python3 jr/ci_watch.py relay-check --base origin/main --head jr/heal-<id> [--body FILE] [--repo DIR]
    python3 jr/ci_watch.py show [--state PATH]
"""
from __future__ import annotations

import argparse
import fcntl
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FAILURE = "FAILURE"
INFRA = ("CANCELLED", "TIMED_OUT", "STARTUP_FAILURE")
SUCCESS = ("SUCCESS", "NEUTRAL", "SKIPPED")
DAILY_DISPATCHES = 2          # per UTC day, all breaks together
MAX_PER_FINGERPRINT = 2       # the same break: first time + one recurrence; the third needs a human
MAX_AUTO_WITHOUT_ACK = 3      # dispatches since a human last ran `ci_watch.py ack`; then the lane halts
STALL_HOURS = 4               # dispatched and still no heal PR: stalled
# Jr never parks work on a person (owner, 2026-11-19: "what else does this project need"). Every stop below
# used to wait for a human; each now has its own way out, bounded by the daily budgets above.
RETRY_AFTER_HOURS = 24        # a stalled job is tried once more a day later; a second stall is given up
ABANDON_DAYS = 7              # a break Jr gave up on is not looked at again for a week, then counts afresh
LIVE = ("open", "dispatched", "pr_opened", "pushed", "needs_human", "stalled")
MAX_CHANGED_LINES = 300
LOG_EXCERPT_LINES = 200
TICK_BRANCH = "jr/tick-"
HEAL_BRANCH = "jr/heal-"
DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "espatlas-jr" / "heal-incidents.json"
AUTONOMY_PATH = Path(__file__).resolve().parent / "autonomy.json"   # jr/autonomy.json, the reviewed switches
STALL_FLAG, STALL_VARIABLE = "stall_dispatch", "JR_STALL_DISPATCH"
BLIND_AFTER = 3          # consecutive `unavailable` ticks before the owner is told the watch is blind

_STAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
_NODE_FAILED = re.compile(r"^(\S+::\S+) FAILED\b|^FAILED (\S+::\S+)|^ERROR (\S+\.py)\b")
_RUN_JOB = re.compile(r"/runs/(\d+)/job/(\d+)")


class StoreError(Exception):
    """The incident store is unreadable: refused, never overwritten."""


@dataclass
class Observation:
    source: str                 # "main" or "tick"
    number: int | None          # PR number (None for main)
    sha: str
    attempt: int
    run_id: int | None
    checks: dict                # check name -> conclusion ("" while pending)
    logs: dict = field(default_factory=dict)   # check name -> job log text (failing ones only)
    jobs: dict = field(default_factory=dict)   # check name -> job id (to fetch a log later)


@dataclass
class Parsed:
    failed: str | None = None
    assertion: str | None = None
    error: str | None = None
    image: str | None = None
    excerpt: str = ""


@dataclass
class Verdict:
    kind: str                   # incident | rerun | none
    source: str | None = None
    check: str | None = None
    fingerprint: str | None = None
    failed: str | None = None
    assertion: str | None = None
    error: str | None = None
    run_id: int | None = None
    first_red_sha: str | None = None
    first_red_number: int | None = None
    red_image: str | None = None
    last_green_sha: str | None = None
    green_image: str | None = None
    log_excerpt: str = ""
    kind_detail: str = ""       # "ci" (a red required check) or "stall" (a lane that produced nothing, SPEC §1b)
    evidence: dict = field(default_factory=dict)   # stall: the yield window, the lane's last stage summary and rejects


# --- a stalled lane (SPEC-jr-self-heal.md §1b, 2026-11-17) ------------------------------------------------
# The yield ledger (jr/yield_ledger.py) says a lane produced nothing over the stall window although it had
# units every tick. That is a break outside any PR, like a red required check: the same store, the same
# claim/ack/caps, the same heal branch and review route; the delegate's prompt branches on `check`.
STALL_CHECK = "stall:"


def stall_fingerprint(lane: str) -> str:
    return hashlib.sha256(f"stall\n{lane}".encode()).hexdigest()


def stall_verdicts(stall: dict | None, stages: list[dict] | None = None, rejects: dict | None = None) -> list[Verdict]:
    """One incident Verdict per stalled lane named by the tick's `stall` ({lanes, stall_ticks, yields})."""
    if not isinstance(stall, dict) or not stall.get("lanes"):
        return []
    names = {"backfill": ("backfill",), "firmware": ("admit", "boardmap"), "topics": ("admit_topics",)}
    out = []
    for lane in stall["lanes"]:
        summaries = {s.get("name"): (s.get("summary") or "")[:400] for s in (stages or [])
                     if s.get("name") in names.get(lane, (lane,))}
        counts = {s.get("name"): dict(s.get("counts") or {}) for s in (stages or []) if s.get("name") in names.get(lane, (lane,))}
        evidence = {"lane": lane, "stall_ticks": stall.get("stall_ticks"),
                    "yield": (stall.get("yields") or {}).get(lane), "window": (stall.get("yields") or {}).get("ticks_in_window"),
                    "stage_summaries": summaries, "stage_counts": counts, "tick_rejects": dict(rejects or {})}
        out.append(Verdict(kind="incident", source="yield", check=f"{STALL_CHECK}{lane}", fingerprint=stall_fingerprint(lane),
                           failed=f"{lane} produced nothing over {stall.get('stall_ticks')} ticks", kind_detail="stall",
                           evidence=evidence))
    return out


def stall_watch(store: "Store", stall: dict | None, yields: dict | None, now: str, dry_run: bool = False,
                stages: list[dict] | None = None, rejects: dict | None = None) -> dict:
    """After the stages: record one incident per stalled lane (the store keeps one per fingerprint while it is
    live) and resolve the stall incidents of every lane that produced over the window. Never raises."""
    try:
        verdicts = stall_verdicts(stall, stages, rejects)
        producing = [lane for lane in ("backfill", "firmware", "topics")
                     if int(((yields or {}).get(lane) or {}).get("produced") or 0) > 0]
        if dry_run:
            return {"status": "ok", "would": [f"record stall incident {v.check}" for v in verdicts]
                    + [f"resolve stall:{lane}" for lane in producing]}
        out = {"status": "ok", "incidents": [], "resolved": []}
        for v in verdicts:
            rec = store.record(v, now)
            out["incidents"].append(rec["id"] if rec else f"{v.check} already open")
        out["resolved"] = store.resolve_producing(producing, now)
        out["nudges"] = store.nudges()
        return out
    except Exception as e:      # noqa: BLE001 — the tick must keep running whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}


# --- reading a job log ------------------------------------------------------------------------------

def _lines(text: str) -> list[str]:
    return [_STAMP.sub("", line) for line in (text or "").splitlines()]


def parse_job_log(text: str) -> Parsed:
    """The first failing pytest node, its first `E` line, the first ##[error] line and the runner
    image (`Image:` + `Version:` of the "Runner Image" group, never the provisioner's)."""
    lines, p = _lines(text), Parsed()
    for i, line in enumerate(lines):
        if line.strip() == "##[group]Runner Image":
            image = version = None
            for nxt in lines[i + 1:i + 6]:
                if nxt.startswith("Image: "):
                    image = nxt[7:].strip()
                elif nxt.startswith("Version: ") and image:
                    version = nxt[9:].strip()
                    break
            p.image = f"{image} {version}" if image and version else image
    start = None
    for i, line in enumerate(lines):
        m = _NODE_FAILED.match(line.strip())
        if m and p.failed is None:
            p.failed, start = next(g for g in m.groups() if g), i
        if line.startswith("##[error]") and p.error is None:
            p.error = line[len("##[error]"):].strip()
    if start is not None:
        for line in lines[start + 1:]:
            if line.startswith("E "):
                p.assertion = line[1:].strip()
                break
        p.excerpt = "\n".join(lines[start:start + LOG_EXCERPT_LINES])
    elif p.error:
        p.excerpt = "\n".join(line for line in lines if line.startswith("##[error]"))[:4000]
    return p


def _normal(text: str | None) -> str:
    text = re.sub(r"0x[0-9a-fA-F]+", "0x_", text or "")
    text = re.sub(r"\d+", "N", text)
    return text[:200]


def fingerprint(check: str, parsed: Parsed) -> str | None:
    """sha256 of the check, the failing node and its first assertion line (or the first error
    line), with addresses and numbers blanked: one break seen at different times is one print."""
    if not (parsed.failed or parsed.assertion or parsed.error):
        return None
    key = "\n".join([check, parsed.failed or "", _normal(parsed.assertion or parsed.error)])
    return hashlib.sha256(key.encode()).hexdigest()


# --- deciding ---------------------------------------------------------------------------------------

def _state(o: Observation, required: list[str]) -> str:
    """pending | green | red | infra for one observation's required checks."""
    got = [str(o.checks.get(c) or "").upper() for c in required]
    if any(g == "" for g in got):
        return "pending"
    if any(g == FAILURE for g in got):
        return "red"
    if any(g in INFRA for g in got):
        return "infra"
    return "green" if all(g in SUCCESS for g in got) else "red"


def _print(o: Observation, required: list[str]) -> tuple[str | None, str | None, Parsed]:
    """(fingerprint, check, parsed log) of an observation's first failing required check."""
    for c in required:
        concl = str(o.checks.get(c) or "").upper()
        if concl == FAILURE or (concl in INFRA and o.attempt >= 2):
            if concl in INFRA:
                parsed = Parsed(error=f"{c} {concl} on attempt {o.attempt}")
                return hashlib.sha256(f"infra\n{c}\n{concl}".encode()).hexdigest(), c, parsed
            parsed = parse_job_log(o.logs.get(c, ""))
            fp = fingerprint(c, parsed) or hashlib.sha256(f"{c}\nno log".encode()).hexdigest()
            return fp, c, parsed
    return None, None, Parsed()


def _green_side(observations: list[Observation], required: list[str]) -> tuple[str | None, str | None]:
    for o in observations:
        if o.source == "main" and _state(o, required) == "green":
            image = None
            for text in o.logs.values():
                image = parse_job_log(text).image or image
            return o.sha, image
    return None, None


def _incident(o_red: Observation, o_first: Observation, fp: str, check: str, parsed: Parsed,
              observations: list[Observation], required: list[str]) -> Verdict:
    green_sha, green_image = _green_side(observations, required)
    return Verdict(kind="incident", source=o_red.source, check=check, fingerprint=fp, failed=parsed.failed,
                   assertion=parsed.assertion, error=parsed.error, run_id=o_red.run_id,
                   first_red_sha=o_first.sha, first_red_number=o_first.number, red_image=parsed.image,
                   last_green_sha=green_sha, green_image=green_image, log_excerpt=parsed.excerpt)


def evaluate(observations: list[Observation], required: list[str]) -> Verdict:
    """The decision for one tick. `observations` are newest first, main and tick mixed."""
    mains = [o for o in observations if o.source == "main" and _state(o, required) != "pending"]
    ticks = [o for o in observations if o.source == "tick" and _state(o, required) != "pending"]
    if mains:
        m = mains[0]
        if _state(m, required) == "infra" and m.attempt < 2:
            return Verdict(kind="rerun", source="main", run_id=m.run_id)
        if _state(m, required) in ("red", "infra"):
            fp, check, parsed = _print(m, required)
            if fp:
                return _incident(m, m, fp, check, parsed, observations, required)
    if ticks:
        t0 = ticks[0]
        if _state(t0, required) == "infra" and t0.attempt < 2:
            return Verdict(kind="rerun", source="tick", run_id=t0.run_id)
        if len(ticks) > 1:
            fp0, check, parsed = _print(t0, required)
            fp1, _, _ = _print(ticks[1], required)
            if fp0 and fp0 == fp1:
                return _incident(t0, ticks[1], fp0, check, parsed, observations, required)
    return Verdict(kind="none")


# --- a tick that keeps aborting (SPEC-jr-self-heal.md §1c, 2026-11-18) -------------------------------------
# Four ticks in a row aborted on the same pending-PR gap (18Z..21Z Nov 18) and nothing reacted but Telegram:
# an aborted tick writes no yield rows, so the stall rule cannot see it, and CI was green. The tick hands its
# outcome here; the second consecutive abort with the same normalised reason is an incident in the same
# store, claim, budget, ack halt and review route as a red check. Aborts that clear by themselves (GitHub
# unreadable or rate-limited, the lock, the call budget) or that only a human can clear (a stuck tick PR,
# branch protection) never open one and never break a streak. A completed tick resolves every live one.
ABORT_CHECK = "abort:"
ABORT_AFTER = 2                 # consecutive identical aborts before an incident
NOT_FOR_THE_DELEGATE = ("gh ", "GitHub rate limit low", "another tick is running", "cannot open tick lock",
                        "budget:", "branch protection:", "a Jr tick PR has been open >")


def abort_kind(reason: str) -> str:
    """`pending-pr-inventory-incomplete`, `typeerror`, `guard-red`: the reason's head, before ':' , ',' or '—'."""
    head = re.split(r"[:,—(]", reason.strip(), maxsplit=1)[0]
    return (re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-")[:40]) or "unknown"


def abort_fingerprint(reason: str) -> str:
    """By kind, not by detail: a tick stuck on the same check is one break even when the detail changes
    every hour (another firmware in the gap, other files in a red guard). The full reasons ride in evidence."""
    return hashlib.sha256(f"abort\n{abort_kind(reason)}".encode()).hexdigest()


def abort_watch(store: "Store", reason: str | None, now: str, dry_run: bool = False) -> dict:
    """After the tick: `reason` is its abort, or None when it completed. Never raises."""
    try:
        if reason is None:
            if dry_run:
                return {"status": "ok", "incidents": [], "resolved": [], "would": ["resolve abort incidents"]}
            return {"status": "ok", "incidents": [], "resolved": store.resolve_aborts(now), "nudges": store.nudges()}
        if reason.startswith(NOT_FOR_THE_DELEGATE):
            return {"status": "ok", "incidents": [], "resolved": [], "skipped": "transient or needs a human"}
        fp, kind = abort_fingerprint(reason), abort_kind(reason)
        if dry_run:
            return {"status": "ok", "incidents": [], "resolved": [], "would": [f"count abort {ABORT_CHECK}{kind}"]}
        streak = store.abort_seen(fp, reason, now)
        out = {"status": "ok", "incidents": [], "resolved": [], "consecutive": streak["count"]}
        if streak["count"] >= ABORT_AFTER:
            v = Verdict(kind="incident", source="tick", check=f"{ABORT_CHECK}{kind}", fingerprint=fp,
                        failed=reason[:400], kind_detail="abort",
                        evidence={"reason": reason[:2000], "consecutive": streak["count"],
                                  "first_seen": streak["first_seen"], "last_seen": now})
            rec = store.record(v, now)
            out["incidents"].append(rec["id"] if rec else f"{v.check} already open")
        out["nudges"] = store.nudges()
        return out
    except Exception as e:      # noqa: BLE001 — the tick's report must print whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}

# --- an open PR the delegate fixes in place (SPEC-jr-self-heal.md §1d, 2026-11-18) -----------------------
# jr/chores.py records `conflict:#<n>` (a code PR conflicting with main) and `review-fix:#<n>` (the agent
# review's BLOCK at the PR's current head). Unlike a CI break, the fix lands on the PR's OWN branch
# (evidence.pr_branch, a fast-forward of evidence.pr_head), so only a launcher that knows that mode claims
# them (`claim --pr-fix`), and only while the reviewed switch allows. They have their own daily budget.
PR_FIX_CHECKS = ("conflict:", "review-fix:", "ci-fix:")
PR_RED_CHECK = "pr-red:"     # a Jr content PR red on a required check: healed on MAIN (the CI launcher), never in place
PR_FIX_DAILY = 4
PR_FIX_FLAG, PR_FIX_VARIABLE = "pr_fix_dispatch", "JR_PR_FIX_DISPATCH"


def is_pr_fix(rec_or_check) -> bool:
    check = rec_or_check if isinstance(rec_or_check, str) else str(((rec_or_check or {}).get("context") or {}).get("check") or "")
    return check.startswith(PR_FIX_CHECKS)


def pr_fix_verdict(kind: str, number: int, branch: str, head: str, evidence: dict | None = None) -> "Verdict":
    """`kind` is "conflict" or "review-fix". One break per PR and kind: the second recurrence after a
    resolution needs a human (MAX_PER_FINGERPRINT), like any other incident."""
    ev = {**(evidence or {}), "pr": int(number), "pr_branch": branch, "pr_head": head}
    return Verdict(kind="incident", source="chores", check=f"{kind}:#{int(number)}",
                   fingerprint=hashlib.sha256(f"{kind}\n#{int(number)}".encode()).hexdigest(),
                   failed=f"PR #{number}: {kind}", kind_detail=kind, evidence=ev)


# --- the incident store (runner-local) ---------------------------------------------------------------

def _exclusive(method):
    """The whole load-modify-save of a Store method runs under the store's lock."""
    @functools.wraps(method)
    def run(self, *args, **kwargs):
        with self._locked():
            return method(self, *args, **kwargs)
    return run


class Store:
    def __init__(self, path: Path = DEFAULT_STATE):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "incidents": {}}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise StoreError(f"unreadable incident store {self.path}: {e}") from None
        if not isinstance(data, dict) or not isinstance(data.get("incidents"), dict):
            raise StoreError(f"incident store {self.path} has no incidents map")
        return data

    @contextmanager
    def _locked(self):
        """One load-modify-save at a time across processes: the hourly tick and the runner's launcher
        both write this store (review B1 of #1681). flock is released by the kernel if a holder dies."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def get(self, incident_id: str) -> dict | None:
        return self._load()["incidents"].get(incident_id)

    @_exclusive
    def record(self, verdict: Verdict, now: str) -> dict | None:
        """A new open incident for `verdict`, or None (not an incident, or this fingerprint is
        already open). A fingerprint that comes back after it was resolved gets a -N suffix."""
        if verdict.kind != "incident" or not verdict.fingerprint:
            return None
        data = self._load()
        base = verdict.fingerprint[:12]
        same = sorted((r for r in data["incidents"].values() if r["fingerprint"] == verdict.fingerprint),
                      key=lambda r: r["first_seen"])
        if same and same[-1]["state"] == "abandoned" and \
                _hours(same[-1].get("abandoned_at") or same[-1]["first_seen"], now) < ABANDON_DAYS * 24:
            return None                      # given up this week: not recorded again, nothing nudged again
        if same and same[-1]["state"] not in ("resolved", "abandoned"):
            live = same[-1]
            # an open PR fix not handed out yet follows the PR's live head: the delegate must start from it
            # (6th review of #1857, 2026-11-19)
            if is_pr_fix(verdict.check or "") and live["state"] == "open":
                ev = live["context"].setdefault("evidence", {})
                new = verdict.evidence or {}
                if new.get("pr_head") and ev.get("pr_head") != new.get("pr_head"):
                    ev.update({k: v for k, v in new.items()})
                    self._save(data)
            return None
        incident_id = base if not same else f"{base}-{len(same) + 1}"
        # the tries since Jr last gave up on this break (a week ago or more): the count starts afresh after it
        last_given_up = max((n for n, r in enumerate(same) if r["state"] == "abandoned"), default=-1)
        tries = len(same) - (last_given_up + 1)
        state = "abandoned" if tries >= MAX_PER_FINGERPRINT else "open"
        rec = {"id": incident_id, "fingerprint": verdict.fingerprint, "branch": HEAL_BRANCH + incident_id,
               "state": state, "first_seen": now, "context": asdict(verdict)}
        if state == "abandoned":
            rec["abandoned_at"] = now
        data["incidents"][incident_id] = rec
        self._save(data)
        return rec

    @_exclusive
    def claim(self, now: str, allow_stall: bool = True, allow_pr_fix: bool = False) -> dict | None:
        """The oldest open incident, marked dispatched, unless today's (UTC) budget is spent. With
        `allow_stall` false (SPEC §5: the `stall_dispatch` switch off, or its kill variable 0) stall
        incidents stay open and are never handed out; CI incidents are unaffected. PR-fix incidents
        (§1d) are handed out only with `allow_pr_fix` (a launcher that pushes to the PR's own branch, and
        the `pr_fix_dispatch` switch), against their own PR_FIX_DAILY budget."""
        data = self._load()
        day = _utc_day(now)
        # the pause after MAX_AUTO_WITHOUT_ACK fruitless dispatches lasts until the next UTC day, not until a
        # person runs `ack`: the daily budgets already bound what a day can cost
        # (a pause written by the older code has no `halted_day`: it ends at the first claim under this code,
        # instead of never — review BLOCK of #1901)
        if data.get("halted") and data.get("halted_day") != day:
            data.update(auto_since_ack=0, halted=False, halt_nudged=False, halted_day=None)
            self._save(data)
        waiting = sorted((r for r in data["incidents"].values() if r["state"] == "open"
                          and (allow_stall or not str(r["context"].get("check") or "").startswith(STALL_CHECK))
                          and (allow_pr_fix or not is_pr_fix(r))),
                         key=lambda r: r["first_seen"])
        if not waiting:
            return None
        if data.get("auto_since_ack", 0) >= MAX_AUTO_WITHOUT_ACK:
            if not data.get("halted"):
                data.update(halted=True, halted_day=day)
                self._save(data)
            return None
        today = [r for r in data["incidents"].values() if _utc_day(r.get("dispatched_at")) == day]
        spent_fix = sum(1 for r in today if is_pr_fix(r))
        spent = len(today) - spent_fix
        waiting = [r for r in waiting if (spent_fix < PR_FIX_DAILY if is_pr_fix(r) else spent < DAILY_DISPATCHES)]
        # one fix at a time per PR: a second fix would start from a head the first one moves (6th review of #1857)
        busy = {((r["context"].get("evidence") or {}).get("pr")) for r in data["incidents"].values()
                if is_pr_fix(r) and r["state"] in ("dispatched", "pushed")}
        waiting = [r for r in waiting if not (is_pr_fix(r) and (r["context"].get("evidence") or {}).get("pr") in busy)]
        if not waiting:
            return None
        rec = waiting[0]
        rec.update(state="dispatched", dispatched_at=now)
        if not is_pr_fix(rec):
            # a PR fix is bounded on its own: its daily budget, and per PR one fix + one recurrence before a
            # human (MAX_PER_FINGERPRINT). It never moves the human-ack brake, so no "credit" logic is needed
            # to keep the lane alive (5th review of #1857, 2026-11-19: every credit rule could be gamed).
            data["auto_since_ack"] = data.get("auto_since_ack", 0) + 1
        self._save(data)
        return rec

    @_exclusive
    def ack(self, now: str) -> None:
        """A human looked: the count of dispatches without one starts again."""
        data = self._load()
        data.update(auto_since_ack=0, halted=False, halt_nudged=False, halted_day=None, acked_at=now)
        self._save(data)

    @_exclusive
    def progress(self, heal_prs: dict, now: str, merged: set | frozenset = frozenset()) -> list[str]:
        """Dispatched incidents: a PR on the incident's branch -> pr_opened; none after STALL_HOURS ->
        stalled. A stalled incident is opened once more RETRY_AFTER_HOURS later; a second stall is
        `abandoned` (given up: no person is asked). A heal PR in `merged` (numbers) is a productive outcome:
        the ack brake starts again (§1d). Returns the ids that stalled or were given up this pass."""
        data, stalled, changed = self._load(), [], False
        for rec in data["incidents"].values():
            if rec["state"] == "stalled" and not rec.get("retried") and \
                    _hours(rec.get("stalled_at"), now) > RETRY_AFTER_HOURS:
                rec.update(state="open", retried=True)
                changed = True
                continue
            if rec["state"] == "pr_opened" and rec.get("pr") in merged and not rec.get("merged"):
                rec["merged"] = True
                data.update(auto_since_ack=0, halted=False, halt_nudged=False)
                changed = True
            if rec["state"] != "dispatched":
                continue
            if rec["branch"] in heal_prs:
                rec.update(state="pr_opened", pr=heal_prs[rec["branch"]])
                changed = True
            elif _hours(rec.get("dispatched_at"), now) > STALL_HOURS:
                _stall(rec, now)
                stalled.append(rec["id"])
                changed = True
        if changed:
            self._save(data)
        return stalled

    @_exclusive
    def nudges(self) -> list[str]:
        """One message per state change since the last call (the tick sends them to Telegram)."""
        data, out = self._load(), []
        for rec in sorted(data["incidents"].values(), key=lambda r: r["first_seen"]):
            if rec.get("nudged_state") == rec["state"]:
                continue
            out.append(_nudge(rec, data.get("auto_since_ack", 0)))
            rec["nudged_state"] = rec["state"]
        if data.get("halted") and not data.get("halt_nudged"):
            out.append(f"🛑 Jr self-heal paused until 00:00 UTC: {MAX_AUTO_WITHOUT_ACK} heal dispatches without a merged "
                       "fix. It resumes by itself; `python3 jr/ci_watch.py ack` on the runner resumes it now.")
            data["halt_nudged"] = True
        if out:
            self._save(data)
        return out

    @_exclusive
    def pr_fix_progress(self, open_prs: dict, active: set, closed: dict, now: str) -> dict:
        """jr/chores.py's view of the PRs behind live PR-fix incidents. `open_prs` {number: head sha},
        `active` {check} the chores still see, `closed` {number: "MERGED"|"CLOSED"} for PRs no longer open.
        A dispatched fix whose PR has a new head -> `pushed`; one with no push after STALL_HOURS -> stalled;
        a live incident whose check is no longer active (two passes in a row, never while dispatched), or
        whose PR closed, -> resolved. PR fixes never touch the human-ack brake (see claim). Returns
        {"pushed", "stalled", "resolved"}."""
        data = self._load()
        out = {"pushed": [], "stalled": [], "resolved": []}
        for rec in data["incidents"].values():
            if not is_pr_fix(rec) or rec["state"] not in LIVE:
                continue
            ev = rec["context"].get("evidence") or {}
            n, check = ev.get("pr"), rec["context"].get("check")
            if n in closed:
                rec.update(state="resolved", resolved_at=now, closed_as=closed[n])
                out["resolved"].append(rec["id"])
                continue
            head = open_prs.get(n)
            # a dispatched fix that pushed a new head is `pushed` FIRST, whatever the condition shows this pass
            if rec["state"] == "dispatched" and head and head != ev.get("pr_head"):
                rec.update(state="pushed", pushed_head=head, pushed_at=now, absent=0)   # absence counts from the push
                out["pushed"].append(rec["id"])
            if check in active:
                rec.pop("absent", None)
                since = rec.get("pushed_at") if rec["state"] == "pushed" else rec.get("dispatched_at")
                if rec["state"] in ("dispatched", "pushed") and _hours(since, now) > STALL_HOURS:
                    _stall(rec, now)                 # tried once more a day later, then given up
                    out["stalled"].append(rec["id"])
                continue
            # the condition is gone this pass. GitHub's merge state blinks (UNKNOWN while it recomputes) and a
            # comment read can fail: only two absent passes in a row resolve, and a fix still in flight
            # (dispatched, no push yet) is never resolved by a blink (3rd review of #1857, 2026-11-19).
            rec["absent"] = int(rec.get("absent") or 0) + 1
            if rec["state"] == "dispatched" or rec["absent"] < 2:
                continue
            rec.update(state="resolved", resolved_at=now)
            out["resolved"].append(rec["id"])
        self._save(data)
        return out

    @_exclusive
    def resolve_pr_red(self, active_fingerprints: set, now: str) -> list[str]:
        """Close a live `pr-red:` incident once no open content PR has shown its failing test for two passes in
        a row, and never while the delegate is working on it (`dispatched`): a PR whose checks are pending
        right after a refresh shows no failure for one pass (4th review of #1857, 2026-11-19)."""
        data, closed = self._load(), []
        for rec in data["incidents"].values():
            if rec["state"] not in LIVE or not str(rec["context"].get("check") or "").startswith(PR_RED_CHECK):
                continue
            if rec["fingerprint"] in active_fingerprints:
                rec.pop("absent", None)
                continue
            rec["absent"] = int(rec.get("absent") or 0) + 1
            if rec["state"] == "dispatched" or rec["absent"] < 2:
                continue
            rec.update(state="resolved", resolved_at=now)
            closed.append(rec["id"])
        self._save(data)
        return closed

    @_exclusive
    def resolve_green(self, green_checks: list[str], now: str) -> list[str]:
        """Close every live incident whose check is green again on main and on the newest tick PR."""
        data, closed = self._load(), []
        for rec in data["incidents"].values():
            if rec["state"] in LIVE and rec["context"].get("check") in green_checks:
                rec.update(state="resolved", resolved_at=now)
                closed.append(rec["id"])
        if closed:
            self._save(data)
        return closed

    @_exclusive
    def resolve_producing(self, lanes: list[str], now: str) -> list[str]:
        """Close every live stall incident of a lane that produced again over the yield window."""
        checks = {f"{STALL_CHECK}{lane}" for lane in lanes}
        data, closed = self._load(), []
        for rec in data["incidents"].values():
            if rec["state"] in LIVE and rec["context"].get("check") in checks:
                rec.update(state="resolved", resolved_at=now)
                closed.append(rec["id"])
        if closed:
            self._save(data)
        return closed

    @_exclusive
    def abort_seen(self, fingerprint: str, reason: str, now: str) -> dict:
        """Count one tick aborted with `fingerprint`: the streak grows while the same abort repeats, and
        starts over at 1 on a different one."""
        data = self._load()
        streak = data.get("abort_streak") or {}
        if streak.get("fingerprint") == fingerprint:
            streak.update(count=int(streak.get("count") or 0) + 1, last_seen=now, reason=reason[:2000])
        else:
            streak = {"fingerprint": fingerprint, "count": 1, "first_seen": now, "last_seen": now, "reason": reason[:2000]}
        data["abort_streak"] = streak
        self._save(data)
        return dict(streak)

    @_exclusive
    def resolve_aborts(self, now: str) -> list[str]:
        """A tick completed: the streak ends and every live abort incident is resolved."""
        data, closed = self._load(), []
        for rec in data["incidents"].values():
            if rec["state"] in LIVE and str(rec["context"].get("check") or "").startswith(ABORT_CHECK):
                rec.update(state="resolved", resolved_at=now)
                closed.append(rec["id"])
        if closed or data.get("abort_streak"):
            data.pop("abort_streak", None)
            self._save(data)
        return closed

    @_exclusive
    def blind(self, why: str, now: str) -> list[str]:
        """Count one tick that could not see CI. The BLIND_AFTER-th in a row nudges, then at most once
        per UTC day while it lasts (2026-11-13: 23 silent `unavailable` ticks went unnoticed)."""
        data = self._load()
        streak = data.get("blind") or {"since": now, "ticks": 0}
        streak.update(ticks=int(streak.get("ticks", 0)) + 1, why=why)
        out = []
        if streak["ticks"] >= BLIND_AFTER and streak.get("nudged_day") != _utc_day(now):
            out.append(f"👁 Jr CI watch blind for {streak['ticks']} ticks since {streak['since']}: {why}. "
                       "Self-heal sees no CI break until this clears.")
            streak["nudged_day"] = _utc_day(now)
        data["blind"] = streak
        self._save(data)
        return out

    @_exclusive
    def seeing(self) -> None:
        """A tick that read CI ends any blind streak."""
        data = self._load()
        if "blind" in data:
            del data["blind"]
            self._save(data)


def _utc_day(stamp) -> str:
    """The UTC calendar day of an ISO timestamp, whatever its offset ("" when unreadable)."""
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


def _hours(start: str | None, now: str) -> float:
    try:
        return (datetime.fromisoformat(now) - datetime.fromisoformat(str(start))).total_seconds() / 3600
    except (TypeError, ValueError):
        return 0.0


def _stall(rec: dict, now: str) -> None:
    """The first time a job produces nothing it is `stalled` (and opened once more a day later); the second
    time it is `abandoned`."""
    if rec.get("retried"):
        rec.update(state="abandoned", abandoned_at=now)
    else:
        rec.update(state="stalled", stalled_at=now)


def _nudge(rec: dict, auto: int) -> str:
    c, i = rec["context"], rec["id"]
    if str(c.get("check") or "").startswith(STALL_CHECK):
        what = f"{c.get('failed') or c.get('check')} (yield {((c.get('evidence') or {}).get('yield') or {})})"
        if rec["state"] == "resolved":
            return f"✅ Jr stall {i} resolved: {str(c.get('check'))[len(STALL_CHECK):]} produced again over the yield window."
    elif str(c.get("check") or "").startswith(ABORT_CHECK):
        what = (f"the tick aborted {(c.get('evidence') or {}).get('consecutive')} times in a row: "
                f"{str(c.get('failed') or '')[:300]}")
        if rec["state"] == "resolved":
            return f"✅ Jr tick-abort incident {i} resolved: a tick completed again."

    elif is_pr_fix(str(c.get("check") or "")):
        ev = c.get("evidence") or {}
        what = f"PR #{ev.get('pr')} needs a {c.get('kind_detail')} fix on its own branch {ev.get('pr_branch')}"
        if rec["state"] == "resolved":
            return f"✅ Jr chore {i} done: PR #{ev.get('pr')} {c.get('kind_detail')} cleared ({rec.get('closed_as') or 'fixed'})."
    else:
        what = f"{c.get('check')} red outside any PR ({c.get('failed') or c.get('error') or 'see log'})"
    return {
        "open": f"🔧 Jr CI incident {i}: {what}. The heal delegate gets it within the hour "
                f"({auto}/{MAX_AUTO_WITHOUT_ACK} automatic dispatches used since a human last looked).",
        "dispatched": f"🔧 Jr heal {i} dispatched on {rec['branch']}; a PR or a stall notice follows within {STALL_HOURS} h.",
        "pr_opened": f"🔧 Jr heal {i}: PR #{rec.get('pr')} is open and needs an independent exact-head review.",
        "pushed": f"🔧 Jr chore {i}: the fix is pushed to {what.split(' on its own branch ')[-1]} at {str(rec.get('pushed_head'))[:8]}; the agent review judges the new head.",
        "resolved": f"✅ Jr CI incident {i} resolved: {c.get('check')} is green on main and on the newest tick PR.",
        "needs_human": f"🛑 Jr CI incident {i}: the same break came back a {MAX_PER_FINGERPRINT + 1}rd time. "
                       f"Nothing is dispatched; it needs a human. {what}.",
        "stalled": f"🛑 Jr heal {i} stalled: nothing {STALL_HOURS} h after dispatch. Jr tries it once more in "
                   f"{RETRY_AFTER_HOURS} h.",
        "abandoned": f"🏳 Jr gave up on incident {i} after {MAX_PER_FINGERPRINT} tries: {what}. Nothing waits on you; "
                     f"Jr does not look at it again for {ABANDON_DAYS} days.",
    }.get(rec["state"], f"Jr CI incident {i}: {rec['state']}")


# --- reading GitHub -----------------------------------------------------------------------------------

def _json(gh, *args):
    p = gh(*args)
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        return json.loads(p.stdout or "null")
    except json.JSONDecodeError:
        return None


def _contexts(data) -> list[str] | None:
    contexts = data.get("contexts") if isinstance(data, dict) else None
    return [str(c) for c in contexts] if isinstance(contexts, list) and contexts else None


def required_checks(gh, slug: str) -> list[str] | None:
    """main's required checks. The branch read works for any token that can read the repo; the
    protection endpoint needs admin rights and answered the tick's own token 404 (2026-11-12/13), so it
    is only the fallback."""
    branch = _json(gh, "api", f"repos/{slug}/branches/main")
    protection = branch.get("protection") if isinstance(branch, dict) else None
    found = _contexts(protection.get("required_status_checks") if isinstance(protection, dict) else None)
    return found or _contexts(_json(gh, "api", f"repos/{slug}/branches/main/protection/required_status_checks"))


def _job_log(gh, slug: str, job_id: str) -> str:
    p = gh("api", f"repos/{slug}/actions/jobs/{job_id}/logs")
    return p.stdout if getattr(p, "returncode", 1) == 0 else ""


def _main_observation(gh, slug: str, required: list[str]) -> Observation | None:
    runs = _json(gh, "run", "list", "--branch", "main", "--workflow", "validate.yml", "--limit", "1",
                 "--json", "databaseId,headSha,attempt,status")
    if not runs:
        return None
    run = runs[0]
    jobs = _json(gh, "api", f"repos/{slug}/actions/runs/{run['databaseId']}/jobs")
    if not isinstance(jobs, dict):
        return None
    checks, logs, ids = {}, {}, {}
    for job in jobs.get("jobs", []):
        name = job.get("name")
        checks[name] = str(job.get("conclusion") or "").upper()
        ids[name] = str(job.get("id"))
        if name in required and checks[name] == FAILURE:       # logs cost a call: failures only
            logs[name] = _job_log(gh, slug, ids[name])
    return Observation("main", None, run.get("headSha", ""), int(run.get("attempt") or 1),
                       run.get("databaseId"), checks, logs, ids)


def _recent_prs(gh) -> list[dict]:
    return _json(gh, "pr", "list", "--state", "all", "--limit", "12",
                 "--json", "number,headRefName,headRefOid,createdAt,state,statusCheckRollup") or []


def _tick_observations(gh, slug: str, required: list[str], prs: list[dict]) -> list[Observation]:
    prs = sorted((p for p in prs if str(p.get("headRefName", "")).startswith(TICK_BRANCH)),
                 key=lambda p: p.get("createdAt", ""), reverse=True)[:3]
    out = []
    for pr in prs:
        checks, logs, run_id, attempt = {}, {}, None, 1
        for c in pr.get("statusCheckRollup") or []:
            name = c.get("name")
            if not name:
                continue
            checks[name] = str(c.get("conclusion") or "").upper()
            m = _RUN_JOB.search(str(c.get("detailsUrl") or ""))
            if name in required and m:
                run_id = int(m.group(1))
                if checks[name] == FAILURE:
                    logs[name] = _job_log(gh, slug, m.group(2))
                elif checks[name] in INFRA:
                    run = _json(gh, "api", f"repos/{slug}/actions/runs/{m.group(1)}")
                    attempt = int((run or {}).get("run_attempt") or 1)
        out.append(Observation("tick", pr.get("number"), pr.get("headRefOid", ""), attempt, run_id, checks, logs))
    return out


def watch(gh, slug: str, store: Store, now: str, dry_run: bool = False) -> dict:
    """One tick's CI watch. Never raises: GitHub or store trouble reads as `unavailable`. About four
    GitHub calls on a green CI; a dry run reruns nothing and writes no store. A watch that stays blind
    says so: the third `unavailable` tick in a row nudges, then at most once per UTC day."""
    out = _watch(gh, slug, store, now, dry_run)
    if dry_run:
        return out
    try:
        if out.get("status") == "unavailable":
            blind = store.blind(out.get("why", ""), now)
            if blind:
                out["nudges"] = blind
        else:
            store.seeing()
    except Exception:           # noqa: BLE001 — the tick must keep running whatever happens here
        pass
    return out


def _watch(gh, slug: str, store: Store, now: str, dry_run: bool) -> dict:
    try:
        required = required_checks(gh, slug)
        if not required:
            return {"status": "unavailable", "why": "required checks unreadable"}
        main = _main_observation(gh, slug, required)
        prs = _recent_prs(gh)
        ticks = _tick_observations(gh, slug, required, prs)
        observations = ([main] if main else []) + ticks
        verdict = evaluate(observations, required)
        out = {"status": "ok", "verdict": verdict.kind}
        if verdict.kind == "incident" and verdict.green_image is None and main and _state(main, required) == "green":
            job = main.jobs.get(verdict.check)
            verdict.green_image = parse_job_log(_job_log(gh, slug, job)).image if job else None
        if dry_run:
            if verdict.kind == "rerun":
                out["would"] = f"rerun {verdict.run_id}"
            elif verdict.kind == "incident":
                out["would"] = "record incident"
            return out
        if verdict.kind == "rerun" and verdict.run_id:
            p = gh("run", "rerun", str(verdict.run_id), "--failed")
            out["rerun"] = verdict.run_id if getattr(p, "returncode", 1) == 0 else f"rerun of {verdict.run_id} failed"
        elif verdict.kind == "incident":
            rec = store.record(verdict, now)
            out["incident"] = rec["id"] if rec else "already open"
        live = [o for o in observations if _state(o, required) != "pending"]
        newest_main = next((o for o in live if o.source == "main"), None)
        newest_tick = next((o for o in live if o.source == "tick"), None)
        if newest_main and newest_tick:
            green = [c for c in required if newest_main.checks.get(c) in SUCCESS and newest_tick.checks.get(c) in SUCCESS]
            out["resolved"] = store.resolve_green(green, now)
        heal_prs = {p["headRefName"]: p.get("number") for p in prs if str(p.get("headRefName", "")).startswith(HEAL_BRANCH)}
        merged = {p.get("number") for p in prs if str(p.get("headRefName", "")).startswith(HEAL_BRANCH)
                  and p.get("state") == "MERGED"}
        # a heal PR merged after 12 newer PRs were opened is still found (5th review of #1857): one extra call
        older = [p for p in (_json(gh, "pr", "list", "--state", "merged", "--search", "head:jr/heal-", "--limit", "30",
                                   "--json", "number,headRefName") or []) if str(p.get("headRefName", "")).startswith(HEAL_BRANCH)]
        merged |= {p.get("number") for p in older}
        heal_prs.update({p["headRefName"]: p.get("number") for p in older if p["headRefName"] not in heal_prs})
        out["stalled"] = store.progress(heal_prs, now, merged)
        out["nudges"] = store.nudges()
        return out
    except Exception as e:      # the tick must keep running whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}


# --- the relay's hard limits (SPEC §3) -------------------------------------------------------------------

_TEST_FILE = re.compile(r"(^|/)test_[^/]*\.py$|(^|/)tests/")
_SKIP = re.compile(r"pytest\.mark\.(skipif|skip|xfail)|pytest\.(skip|xfail)\(")
# Deselecting a test by configuration is a skip by another name (review N2 of #1681).
_SELECTION_FILE = re.compile(r"(^|/)(conftest\.py|pytest\.ini)$")
_SELECTION_CONFIG = re.compile(r"^\.github/workflows/|(^|/)(pyproject\.toml|setup\.cfg|tox\.ini)$")
_SELECTION_LINE = re.compile(r"pytest|addopts|testpaths|norecursedirs|python_files|--deselect|--ignore")


def _justified(body: str, marker: str, path: str) -> bool:
    return marker in body and path in body


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _changes(repo: Path, base: str, head: str, pr_fix: bool, fmt: str) -> list[str]:
    """The diff lines (`fmt`: --numstat, --name-status or -U0) the delegate is answerable for. Heal mode:
    everything since the merge base with `base` (main). PR-fix mode: each commit in base..head on top of
    the PR head; a merge counts only its conflict resolution (`git show --remerge-diff`), never what main
    brings into the PR."""
    if not pr_fix:
        return _git(repo, "diff", fmt, "--no-renames", f"{base}...{head}").splitlines()
    out = []
    # --first-parent: the delegate's own commits; a merge's second parent brings main's, never theirs
    for c in _git(repo, "rev-list", "--first-parent", "--reverse", f"{base}..{head}").split():
        merge = len(_git(repo, "rev-list", "--parents", "-n", "1", c).split()) > 2
        args = ["show", "--format=", fmt, "--no-renames"] + (["--remerge-diff"] if merge else []) + [c]
        out += _git(repo, *args).splitlines()
    return out


def _merges_only_main(repo: Path, base: str, head: str, main_ref: str) -> list[str]:
    """Every merge among the delegate's first-parent commits must have exactly two parents and bring in only
    `main` (its second parent an ancestor of `main_ref`): a clean merge of any other branch shows nothing in
    --remerge-diff and would smuggle its changes past every rule (review BLOCK of #1857, 2026-11-19)."""
    out = []
    for c in _git(repo, "rev-list", "--first-parent", "--reverse", f"{base}..{head}").split():
        parents = _git(repo, "rev-list", "--parents", "-n", "1", c).split()[1:]
        if len(parents) > 2:
            out.append(f"{c[:12]} is an octopus merge")
        elif len(parents) == 2 and subprocess.run(["git", "merge-base", "--is-ancestor", parents[1], main_ref],
                                                  cwd=repo, capture_output=True).returncode != 0:
            out.append(f"{c[:12]} merges {parents[1][:12]}, which is not on main")
    return out


def relay_problems(repo: Path, base: str, head: str, body: str = "", pr_fix: bool = False,
                   main_ref: str = "origin/main") -> list[str]:
    """Why the heal branch `head` must not be pushed (empty list: it may). `pr_fix` (§1d): `base` is the PR
    head the fix started from; `head` must fast-forward it, any merge may bring in only `main_ref`, and only
    the delegate's own changes count."""
    problems = []
    if pr_fix and subprocess.run(["git", "merge-base", "--is-ancestor", base, head], cwd=repo,
                                 capture_output=True).returncode != 0:
        return [f"{head} is not a fast-forward of the PR head {base}"]
    if pr_fix:
        bad = _merges_only_main(repo, base, head, main_ref)
        if bad:
            return bad
    total = 0
    for line in _changes(repo, base, head, pr_fix, "--numstat"):
        added, deleted, path = line.split("\t", 2)
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    if total > MAX_CHANGED_LINES:
        problems.append(f"changes {total} lines, more than {MAX_CHANGED_LINES}")
    for line in _changes(repo, base, head, pr_fix, "--name-status"):
        status, path = line.split("\t", 1)
        if path.startswith("data/"):
            problems.append(f"touches data/: {path}")
        if path.startswith("docs/demand/"):
            problems.append(f"touches docs/demand/: {path}")
        if status == "D" and _TEST_FILE.search(path):
            problems.append(f"deletes test file {path}")
        if _SELECTION_FILE.search(path) and not _justified(body, "Test selection changed:", path):
            problems.append(f"changes test selection in {path} without 'Test selection changed:' naming it in the PR body")
    current = None
    for line in _changes(repo, base, head, pr_fix, "-U0"):
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            continue
        if line.startswith("--- "):
            if line.startswith("--- a/"):
                current = line[6:]
            continue
        if not current:
            continue
        if current.startswith(".github/workflows/") and line[:1] in "+-" and re.search(r"permissions|secrets\.", line):
            problems.append(f"workflow permissions or secrets changed in {current}")
        if (_SELECTION_CONFIG.search(current) and line[:1] in "+-" and _SELECTION_LINE.search(line)
                and not _justified(body, "Test selection changed:", current)):
            problems.append(f"changes test selection in {current} without 'Test selection changed:' naming it in the PR body")
        if line.startswith("+") and current.endswith(".py"):
            m = _SKIP.search(line)
            if m:
                problems.append(f"adds {m.group(0)} in {current}")
        if line.startswith("-") and line[1:].strip().startswith("assert "):
            if not _justified(body, "Assertion changed:", current):
                problems.append(f"removes an assert in {current} without 'Assertion changed:' naming it in the PR body")
    return sorted(set(problems))


# --- CLI for the operator's launcher and relay --------------------------------------------------------------

def stall_dispatch_allowed(autonomy_path: Path, env) -> bool:
    """SPEC-jr-self-heal.md §5: a stall incident reaches the delegate only when `jr/autonomy.json` has
    `stall_dispatch: true` (a reviewed PR) AND the variable JR_STALL_DISPATCH is not 0 (the instant kill).
    Unreadable file or flag absent: off. CI incidents never consult this."""
    try:
        doc = json.loads(Path(autonomy_path).read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(doc, dict) or doc.get(STALL_FLAG) is not True:
        return False
    return str(env.get(STALL_VARIABLE, "1")).strip() != "0"


def pr_fix_dispatch_allowed(autonomy_path: Path, env) -> bool:
    """SPEC-jr-self-heal.md §1d: a PR-fix incident reaches the delegate only when `jr/autonomy.json` has
    `pr_fix_dispatch: true` (a reviewed PR) AND JR_PR_FIX_DISPATCH is not 0 (the instant kill)."""
    try:
        doc = json.loads(Path(autonomy_path).read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(doc, dict) or doc.get(PR_FIX_FLAG) is not True:
        return False
    return str(env.get(PR_FIX_VARIABLE, "1")).strip() != "0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ci_watch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "show", "ack"):
        s = sub.add_parser(name)
        s.add_argument("--state", type=Path, default=DEFAULT_STATE)
        if name == "claim":
            s.add_argument("--pr-fix", action="store_true",
                           help="this launcher pushes PR-fix incidents to the PR's own branch (§1d)")
    r = sub.add_parser("relay-check")
    r.add_argument("--base", required=True)
    r.add_argument("--head", required=True)
    r.add_argument("--body", type=Path)
    r.add_argument("--repo", type=Path, default=Path.cwd())
    r.add_argument("--pr-fix", action="store_true", help="base is the PR head; judge only the delegate's commits (§1d)")
    r.add_argument("--main", default="origin/main", help="the ref a PR-fix merge may bring in (default origin/main)")
    args = ap.parse_args(argv)
    if args.cmd == "relay-check":
        body = args.body.read_text() if args.body else ""
        problems = relay_problems(args.repo, args.base, args.head, body, pr_fix=args.pr_fix, main_ref=args.main)
        for p in problems:
            print(f"REFUSED: {p}")
        return 1 if problems else 0
    store = Store(args.state)
    if args.cmd == "ack":
        store.ack(_now())
        print("acknowledged: automatic heal dispatches may resume")
        return 0
    if args.cmd == "claim":
        rec = store.claim(_now(), allow_stall=stall_dispatch_allowed(AUTONOMY_PATH, os.environ),
                          allow_pr_fix=args.pr_fix and pr_fix_dispatch_allowed(AUTONOMY_PATH, os.environ))
        if rec is None:
            return 3
        print(json.dumps(rec, indent=2))
        return 0
    print(json.dumps(store._load(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
