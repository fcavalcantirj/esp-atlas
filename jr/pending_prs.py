"""EspAtlas Jr — what Jr's own tick PRs already hold (jr/pending_prs.py).

ONE question: is firmware X already sitting in a Jr tick PR the owner has not settled — or one the
owner closed unmerged (a veto) less than VETO_TTL_DAYS ago? If so, no stage may propose X again: not
its record, not a recipe for it on any board. While the PR is OPEN no stage edits X's files at all
(a second edit of the same file would conflict with it).

Why not the ledger: a tick starts from a fresh worktree at origin/main. tick.hydrate_open_pr_ledger
writes `proposed` for an open PR's ids, but memory refuses that write over a `merged` record — and
an already-catalogued firmware widened by boardmap IS merged. So nothing marked it pending, and
every hourly tick re-derived the same recipes into another jr-review PR (#1500 … #1511,
nightdriverstrip). A veto of a PR whose proposal never reached main was forgotten the same way.

The source of truth is GitHub's own changed-file list of each PR (read-only): the open list is the
preflight's `gh pr list --state open` (it already carries `files`), the vetoes one more counted
`gh pr list --state closed`. Firmware ids come from data/firmware/<id>/… and
data/recipes/<board>__<id>/… paths. A veto rejects what the PR PROPOSED for an id — a recipe (every
new firmware ships one) or mapped signals; a closed PR that only rewrote a catalogued record's
firmware.md (a popularity refresh) vetoes nothing for it. Nothing is persisted: the index is rebuilt every tick, so a
merge or a lapsed veto releases the firmware on its own.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VETO_TTL_DAYS = 30        # the tick PR body's promise: "Close = veto … does not propose it again for 30 days"
CLOSED_PR_LIMIT = 200     # closed-unmerged tick PRs inside the TTL (11 in the 30 days to 2026-11-07)
TICK_BRANCH_PREFIX = "jr/tick-"
OPEN, VETOED = "open", "vetoed"

_FIRMWARE_PATH_RE = re.compile(r"^data/firmware/([^/]+)/")
_RECIPE_PATH_RE = re.compile(r"^data/recipes/[^/]+__([^/]+)/")
_RECORD_ONLY_RE = re.compile(r"^data/firmware/[^/]+/firmware\.md$")


@dataclass(frozen=True)
class Hold:
    """Firmware `firmware` is held by tick PR `pr_ref`, open or vetoed (closed unmerged)."""
    firmware: str
    pr_ref: str
    state: str
    until: datetime | None = None        # a veto's lapse; None for an open PR

    @property
    def reason(self) -> str:
        return "already_proposed" if self.state == OPEN else "vetoed"

    @property
    def note(self) -> str:
        if self.state == OPEN:
            return f"{self.pr_ref} open"
        return f"{self.pr_ref} closed unmerged, veto until {self.until:%Y-%m-%d}"


@dataclass(frozen=True)
class PendingIndex:
    holds: dict = field(default_factory=dict)     # firmware id -> Hold
    truncated: bool = False                       # the closed list hit CLOSED_PR_LIMIT: older vetoes unseen

    def hold(self, firmware_id: str | None) -> Hold | None:
        return self.holds.get(firmware_id) if firmware_id else None

    def __len__(self) -> int:
        return len(self.holds)


EMPTY = PendingIndex()


def of(ctx) -> PendingIndex:
    """The tick's index on a stage context; EMPTY for a context built without one."""
    return getattr(ctx, "pending", None) or EMPTY


def firmware_ids(paths) -> set[str]:
    """The firmware ids a set of changed paths names: its records and its recipes."""
    ids = set()
    for path in paths:
        m = _FIRMWARE_PATH_RE.match(path) or _RECIPE_PATH_RE.match(path)
        if m:
            ids.add(m.group(1))
    return ids


def proposed_ids(paths) -> set[str]:
    """The ids a closed PR proposed something for: every id but one whose ONLY change was its own
    firmware.md — a refresh of a catalogued record (a new firmware always ships its first recipe)."""
    paths = list(paths)
    return firmware_ids(p for p in paths if not _RECORD_ONLY_RE.match(p))


def _paths(pr: dict) -> list[str]:
    return [str(f.get("path") or "") for f in (pr.get("files") or []) if isinstance(f, dict)]


def _is_tick_pr(pr: dict) -> bool:
    return str(pr.get("headRefName", "")).startswith(TICK_BRANCH_PREFIX)


def _when(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _veto_until(pr: dict, now: datetime) -> datetime | None:
    """When a closed tick PR's veto lapses, or None when it is no live veto (merged, undated, lapsed)."""
    if pr.get("mergedAt"):
        return None
    closed = _when(pr.get("closedAt"))
    if closed is None:
        return None
    until = closed + timedelta(days=VETO_TTL_DAYS)
    return until if until > now else None


def build(open_prs: list, closed_prs: list, now: datetime, truncated: bool = False) -> PendingIndex:
    """The index over open tick PRs and closed-unmerged ones still inside VETO_TTL_DAYS. An open PR
    wins over a veto of the same firmware; among vetoes, the one that lapses last."""
    holds: dict = {}
    for pr in closed_prs:
        until = _veto_until(pr, now) if _is_tick_pr(pr) else None
        if until is None:
            continue
        for fid in proposed_ids(_paths(pr)):
            if fid not in holds or until > holds[fid].until:
                holds[fid] = Hold(fid, f"#{pr.get('number')}", VETOED, until)
    for pr in open_prs:
        if _is_tick_pr(pr):
            for fid in firmware_ids(_paths(pr)):
                holds[fid] = Hold(fid, f"#{pr.get('number')}", OPEN)
    return PendingIndex(holds, truncated)


def list_closed_tick_prs(gh, now: datetime) -> list | None:
    """Closed-unmerged PRs closed inside the veto TTL, with their files (one counted call), or None
    when unreadable. build() re-checks every date and branch: the search only narrows the list."""
    since = (now - timedelta(days=VETO_TTL_DAYS)).date().isoformat()
    p = gh("pr", "list", "--state", "closed", "--limit", str(CLOSED_PR_LIMIT),
           "--search", f"is:unmerged closed:>={since}",
           "--json", "number,headRefName,closedAt,mergedAt,files")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        prs = json.loads(getattr(p, "stdout", "") or "[]")
    except json.JSONDecodeError:
        return None
    return [pr for pr in prs if isinstance(pr, dict)] if isinstance(prs, list) else None


def load(gh, open_prs: list, now: datetime) -> PendingIndex | None:
    """The tick's index from the preflight's open-PR list plus the closed-unmerged ones; None when
    GitHub is unreadable — the caller fails closed (a tick blind to its PRs must not open another)."""
    closed = list_closed_tick_prs(gh, now)
    return None if closed is None else build(open_prs, closed, now, truncated=len(closed) >= CLOSED_PR_LIMIT)
