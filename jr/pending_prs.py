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

Identity is the repository, not its name: an upstream rename turns `oldtool` into `newtool` while
GitHub's numeric repository id stays. A hold keeps that id and its slug as the alias it was proposed
under, and match() looks a candidate up by id BEFORE slug. The id comes from the jr/proposed_ledger.json
committed at the PR's head (one raw contents read, only when the PR changes that ledger) and from
nowhere else: a PR body is editable by anyone who can edit the PR, so its hidden identity marker
(render_identity) is never trusted alone — a marker id the ledger contradicts or does not record is
ignored, and a PR without a marker (one older than it) is verified the same way. A body whose marker
is ambiguous — opened twice, a firmware named twice, unreadable — is a gap: the tick fails closed
before anything is written. An unreadable committed ledger is a gap too; a record without the id
leaves it unknown and the hold matched by slug. When id and slug disagree — the held slug under
another id — or a slug collides where either id is unknown, the candidate is held, never admitted:
name similarity is never identity.

An index that may miss a hold is as blind as an unreadable one, so it names its gaps and the tick
fails closed on any: an open or closed list that returned its full limit (it may be cut), or a held
tick PR whose file list cannot be shown whole. `gh pr list --json files` carries only a PR's first
100 files, so a tick PR whose `files` fall short of its `changedFiles` is re-read through the REST
listing, paginated, and must then match its count exactly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

VETO_TTL_DAYS = 30        # the tick PR body's promise: "Close = veto … does not propose it again for 30 days"
CLOSED_PR_LIMIT = 200     # closed-unmerged tick PRs inside the TTL (11 in the 30 days to 2026-11-07)
REST_FILES_CAP = 3000     # GitHub's REST pulls/<n>/files lists at most this many files of a PR
PR_LIST_FIELDS = "files,changedFiles,body,headRefOid"   # changedFiles proves `files` whole; body carries the
                                                         # identity marker; headRefOid pins the committed ledger
LEDGER_PATH = "jr/proposed_ledger.json"
RAW_MEDIA = "Accept: application/vnd.github.raw+json"   # the contents API answers with the file itself
TICK_BRANCH_PREFIX = "jr/tick-"
OPEN, VETOED = "open", "vetoed"
AMBIGUOUS = "identity_ambiguous"
IDENTITY_MARKER = "jr-identity"

_FIRMWARE_PATH_RE = re.compile(r"^data/firmware/([^/]+)/")
_RECIPE_PATH_RE = re.compile(r"^data/recipes/[^/]+__([^/]+)/")
_RECORD_ONLY_RE = re.compile(r"^data/firmware/[^/]+/firmware\.md$")
_IDENTITY_RE = re.compile(r"<!--\s*" + IDENTITY_MARKER + r":\s*(.*?)\s*-->", re.S)
_IDENTITY_OPEN_RE = re.compile(r"<!--\s*" + IDENTITY_MARKER + r"\s*:")
_GITHUB_PREFIX = "https://github.com/"


@dataclass(frozen=True)
class Hold:
    """Firmware `firmware` is held by tick PR `pr_ref`, open or vetoed (closed unmerged)."""
    firmware: str
    pr_ref: str
    state: str
    until: datetime | None = None        # a veto's lapse; None for an open PR
    repo_id: int | None = None           # GitHub's stable repository id the PR verified; None = unknown
    repo: str | None = None              # owner/repo it was proposed under (the slug alias)
    seen_as: str | None = None           # match(): the candidate's own slug, when renamed since
    seen_id: int | None = None           # match(): the candidate's other id under this slug (ambiguous)

    @property
    def reason(self) -> str:
        if self.seen_id is not None:
            return AMBIGUOUS
        return "already_proposed" if self.state == OPEN else "vetoed"

    @property
    def note(self) -> str:
        where = (f"{self.pr_ref} open" if self.state == OPEN
                 else f"{self.pr_ref} closed unmerged, veto until {self.until:%Y-%m-%d}")
        if self.seen_id is not None:
            return (f"{self.firmware} is repo id {self.repo_id} in {where}; this one is repo id "
                    f"{self.seen_id}: held for the owner, never admitted")
        if self.seen_as is not None:
            return f"{where}; repo id {self.repo_id}, proposed as {self.firmware} ({self.repo}), renamed {self.seen_as}"
        return where


@dataclass(frozen=True)
class PendingIndex:
    holds: dict = field(default_factory=dict)     # firmware id -> Hold
    gaps: tuple = ()                              # why a hold may be unseen; any gap = fail closed
    by_repo_id: dict = field(default_factory=dict)   # verified GitHub repository id -> Hold

    def hold(self, firmware_id: str | None) -> Hold | None:
        return self.holds.get(firmware_id) if firmware_id else None

    def match(self, firmware_id: str | None, repo_id) -> Hold | None:
        """The hold on a candidate whose GitHub id is `repo_id` (None when unread): by stable id first —
        under another slug it is the held repository renamed (`seen_as`) — then by slug. A held slug
        verified under ANOTHER id is ambiguous (`seen_id`, reason identity_ambiguous); an id unknown
        on either side of a slug collision keeps the hold. Never None where a hold might apply."""
        rid = repo_id if type(repo_id) is int else None
        by_id = self.by_repo_id.get(rid) if rid is not None else None
        if by_id is not None:
            return by_id if by_id.firmware == firmware_id else replace(by_id, seen_as=firmware_id)
        hold = self.hold(firmware_id)
        if hold is None or hold.repo_id is None or rid is None:
            return hold
        return replace(hold, seen_id=rid)

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


def render_identity(items) -> str:
    """The hidden comment a tick PR body carries: the GitHub repository id admission verified for each
    firmware it proposes. "" when none carries one (a recipe-only PR, a firmware without an id)."""
    ids = [{"id": it["id"], "repo": str(it.get("url") or "").removeprefix(_GITHUB_PREFIX).lower() or None,
            "repo_id": it["repo_id"]}
           for it in items if it.get("kind") == "firmware" and it.get("id") and type(it.get("repo_id")) is int]
    if not ids:
        return ""
    payload = (json.dumps(ids, sort_keys=True).replace("<", "\\u003c")     # no second marker opening inside
               .replace("-->", "--\\u003e"))                                 # a "-->" must not end the comment
    return f"<!-- {IDENTITY_MARKER}: {payload} -->"


def defang(text: str) -> str:
    """`text` with every identity-marker opening escaped (`&lt;` renders as `<`): third-party text in
    a tick PR body — a launcher name, a stage summary — must never open a second marker."""
    return _IDENTITY_OPEN_RE.sub(lambda m: "&lt;" + m.group(0)[1:], text)


def identities(body) -> dict | None:
    """{firmware id: (repo id, owner/repo)} a PR body's identity marker CLAIMS — never proof on its own
    (load() accepts only what the committed ledger records). {} when the body has no marker; None when
    the marker is ambiguous: opened more than once (a forged, duplicate or unclosed one in item text),
    unreadable, or naming a firmware twice."""
    opened = len(_IDENTITY_OPEN_RE.findall(body)) if isinstance(body, str) else 0
    if opened == 0:
        return {}
    m = _IDENTITY_RE.search(body)
    try:
        entries = json.loads(m.group(1)) if opened == 1 and m else None
    except json.JSONDecodeError:
        return None
    if not isinstance(entries, list):
        return None
    out = {}
    for e in entries:
        fid, rid = (e.get("id"), e.get("repo_id")) if isinstance(e, dict) else (None, None)
        if not isinstance(fid, str) or type(rid) is not int:
            continue
        if fid in out:
            return None
        out[fid] = (rid, e.get("repo") if isinstance(e.get("repo"), str) else None)
    return out


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


def _held(pr: dict, ids, state: str, until: datetime | None) -> list[Hold]:
    """PR `pr`'s holds on `ids`, each with the repository id load() verified for it from the ledger
    committed at its head (`_identities`); unknown for any other — a body marker is never proof."""
    verified = pr.get("_identities") or {}
    return [Hold(fid, f"#{pr.get('number')}", state, until, *verified.get(fid, (None, None))) for fid in sorted(ids)]


def _wins(new: Hold, old: Hold | None) -> bool:
    """An open PR wins over a veto (the later listed open PR over another); among vetoes, the one
    that lapses last."""
    if old is None or new.state == OPEN:
        return True
    return old.state == VETOED and new.until > old.until


def build(open_prs: list, closed_prs: list, now: datetime, gaps: tuple = ()) -> PendingIndex:
    """The index over open tick PRs and closed-unmerged ones still inside VETO_TTL_DAYS, by firmware
    id and by verified repository id. An open PR wins over a veto of the same firmware; among
    vetoes, the one that lapses last."""
    found: list[Hold] = []
    for pr in closed_prs:
        until = _veto_until(pr, now) if _is_tick_pr(pr) else None
        if until is not None:
            found += _held(pr, proposed_ids(_paths(pr)), VETOED, until)
    for pr in open_prs:
        if _is_tick_pr(pr):
            found += _held(pr, firmware_ids(_paths(pr)), OPEN, None)
    holds: dict = {}
    by_repo_id: dict = {}
    for h in found:
        if _wins(h, holds.get(h.firmware)):
            holds[h.firmware] = h
        if h.repo_id is not None and _wins(h, by_repo_id.get(h.repo_id)):
            by_repo_id[h.repo_id] = h
    return PendingIndex(holds, tuple(gaps), by_repo_id)


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


def _ledger_identities(gh, slug: str, pr: dict, ids) -> dict | None:
    """{firmware id: (repo id, owner/repo)} the ledger committed at `pr`'s head records for `ids` (one
    raw contents read); None when unreadable. A record without an int repo_id verifies nothing."""
    oid = pr.get("headRefOid")
    if not slug or not isinstance(oid, str) or not oid:
        return None
    p = gh("api", "-H", RAW_MEDIA, f"repos/{slug}/contents/{LEDGER_PATH}?ref={oid}")
    try:
        led = json.loads(getattr(p, "stdout", "") or "") if getattr(p, "returncode", 1) == 0 else None
    except json.JSONDecodeError:
        return None
    by_id = led.get("by_id") if isinstance(led, dict) else None
    if not isinstance(by_id, dict):
        return None
    out = {}
    for fid in ids:
        rec = by_id.get(fid)
        rid = rec.get("repo_id") if isinstance(rec, dict) else None
        if type(rid) is int:
            repo = rec.get("repo")
            out[fid] = (rid, repo.lower() if isinstance(repo, str) else None)
    return out


def _verified(gh, slug: str, prs: list, held_ids, gaps: list) -> list:
    """`prs`, each with the identities verified for the firmware it holds (`held_ids(paths)`): what the
    ledger committed at its head records, when the PR changes that ledger; none otherwise. The body
    marker only claims: an ambiguous one on a PR that holds something, or a ledger that cannot be
    read, is a gap and its PR dropped. A PR that holds nothing decides nothing, whatever its body."""
    out = []
    for pr in prs:
        n, paths = pr.get("number"), _paths(pr)
        held, verified = held_ids(paths), {}
        if held and identities(pr.get("body")) is None:
            gaps.append(f"Jr PR #{n}'s identity marker is ambiguous (opened twice, a firmware named twice "
                        "or unreadable)")
            continue
        if held and LEDGER_PATH in paths:
            verified = _ledger_identities(gh, slug, pr, held)
            if verified is None:
                gaps.append(f"Jr PR #{n}'s committed {LEDGER_PATH} cannot be read")
                continue
        out.append({**pr, "_identities": verified})
    return out


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
    opened = _verified(gh, slug, opened, firmware_ids, gaps)
    vetoes = _verified(gh, slug, vetoes, proposed_ids, gaps)
    return build(opened, vetoes, now, tuple(gaps))
