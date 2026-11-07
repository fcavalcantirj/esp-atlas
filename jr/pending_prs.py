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

An index that may miss a hold is as blind as an unreadable one, so it names its gaps and the tick
fails closed on any: an open or closed list that returned its full limit (it may be cut), or a held
tick PR whose file list cannot be shown whole. `gh pr list --json files` carries only a PR's first
100 files, so a tick PR whose `files` fall short of its `changedFiles` is re-read through the REST
listing, paginated, and must then match its count exactly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VETO_TTL_DAYS = 30        # the tick PR body's promise: "Close = veto … does not propose it again for 30 days"
CLOSED_PR_LIMIT = 200     # closed-unmerged tick PRs inside the TTL (11 in the 30 days to 2026-11-07)
REST_FILES_CAP = 3000     # GitHub's REST pulls/<n>/files lists at most this many files of a PR
PR_LIST_FIELDS = "files,changedFiles"   # both lists: changedFiles proves a listed `files` whole
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
    gaps: tuple = ()                              # why a hold may be unseen; any gap = fail closed

    def hold(self, firmware_id: str | None) -> Hold | None:
        return self.holds.get(firmware_id) if firmware_id else None

    def __len__(self) -> int:
        return len(self.holds)

    @property
    def complete(self) -> bool:
        return not self.gaps


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


def build(open_prs: list, closed_prs: list, now: datetime, gaps: tuple = ()) -> PendingIndex:
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
    return PendingIndex(holds, tuple(gaps))


def list_closed_tick_prs(gh, now: datetime) -> list | None:
    """Closed-unmerged PRs closed inside the veto TTL, with their files (one counted call), or None
    when unreadable. build() re-checks every date and branch: the search only narrows the list."""
    since = (now - timedelta(days=VETO_TTL_DAYS)).date().isoformat()
    p = gh("pr", "list", "--state", "closed", "--limit", str(CLOSED_PR_LIMIT),
           "--search", f"is:unmerged closed:>={since}",
           "--json", f"number,headRefName,closedAt,mergedAt,{PR_LIST_FIELDS}")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        prs = json.loads(getattr(p, "stdout", "") or "[]")
    except json.JSONDecodeError:
        return None
    return [pr for pr in prs if isinstance(pr, dict)] if isinstance(prs, list) else None


def _json_pages(text: str) -> list | None:
    """`gh api --paginate` output: JSON arrays printed back to back, flattened; None when unreadable
    (empty output included: an empty listing is `[]`)."""
    decoder, entries, i, text = json.JSONDecoder(), [], 0, text.strip()
    if not text:
        return None
    while i < len(text):
        try:
            page, i = decoder.raw_decode(text, i)
        except ValueError:
            return None
        if not isinstance(page, list):
            return None
        entries += page
        while i < len(text) and text[i].isspace():
            i += 1
    return entries


def _rest_paths(gh, slug: str, number) -> list[str] | None:
    """Every changed path of PR `number` from the paginated REST listing, or None when unreadable."""
    p = gh("api", f"repos/{slug}/pulls/{number}/files?per_page=100", "--paginate")
    entries = _json_pages(getattr(p, "stdout", "") or "") if getattr(p, "returncode", 1) == 0 else None
    if entries is None or not all(isinstance(e, dict) and isinstance(e.get("filename"), str) for e in entries):
        return None
    return [e["filename"] for e in entries]


def _whole(gh, slug: str, pr: dict) -> dict | None:
    """`pr` with its whole file list, or None when it cannot be shown whole. The listed `files` are
    whole when they number exactly `changedFiles`; otherwise the REST listing must."""
    count = pr.get("changedFiles")
    if type(count) is not int or count < 0:
        return None
    if isinstance(pr.get("files"), list) and len(pr["files"]) == count:
        return pr
    if count > REST_FILES_CAP or not slug:
        return None
    paths = _rest_paths(gh, slug, pr.get("number"))
    return None if paths is None or len(paths) != count else {**pr, "files": [{"path": p} for p in paths]}


def _list_gaps(open_prs: list, closed: list, open_limit: int) -> list[str]:
    gaps = []
    if len(open_prs) >= open_limit:
        gaps.append(f"open PR list hit its limit of {open_limit}: an open Jr PR may be unseen")
    if len(closed) >= CLOSED_PR_LIMIT:
        gaps.append(f"closed PR list hit its limit of {CLOSED_PR_LIMIT}: a veto may be unseen")
    return gaps


def _shown_whole(gh, slug: str, prs: list, gaps: list) -> list:
    """`prs`, each with its whole file list; one that cannot be shown whole is dropped as a gap."""
    out = []
    for pr in prs:
        whole = _whole(gh, slug, pr)
        if whole is None:
            gaps.append(f"Jr PR #{pr.get('number')}'s changed files cannot be listed whole")
        else:
            out.append(whole)
    return out


def load(gh, open_prs: list, now: datetime, *, slug: str, open_limit: int) -> PendingIndex | None:
    """The tick's index from the preflight's open-PR list (asked for at most `open_limit`) plus the
    closed-unmerged ones; None when GitHub is unreadable — the caller fails closed (a tick blind to
    its PRs must not open another). Every tick PR that can hold something is shown whole first; one
    that cannot, or a list that may be cut, is a gap the caller fails closed on too."""
    closed = list_closed_tick_prs(gh, now)
    if closed is None:
        return None
    gaps = _list_gaps(open_prs, closed, open_limit)
    if gaps:
        return build([], [], now, tuple(gaps))
    opened = _shown_whole(gh, slug, [pr for pr in open_prs if _is_tick_pr(pr)], gaps)
    vetoes = _shown_whole(gh, slug, [pr for pr in closed if _is_tick_pr(pr) and _veto_until(pr, now)], gaps)
    return build(opened, vetoes, now, tuple(gaps))
