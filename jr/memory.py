"""EspAtlas Jr — memory v2 (jr/memory.py): the proposed-ledger with time-bounded decisions.

Phase 2 of the rebuild (docs: SPEC-jr-gate-at-ingest.md, JR.md §6 "Memory — what Jr keeps").
This module is the hourly tick's memory. It is a thin, ADDITIVE layer over jr/ledger.py and the
same on-disk file, jr/proposed_ledger.json — it does not fork the ledger, it extends it:

    {"by_id": {"<firmware_id>": {"id", "repo", "status", "timestamp", "pr_ref"
                                [, "reason"] [, "expires"] [, "expired_at"] [, "repo_id"]
                                [, "evidence_url"] [, "review"] [, "history"]}, ...},
     "by_repo": {"<owner/repo>": "<firmware_id>", ...}}

What v2 adds, and why each field exists:

- `expires` (ISO-8601 UTC, optional). A rejection or a "seen" note that carries a TTL. The old
  ledger had TTL-less `seen` records: a repo scored below the floor in August stayed skipped for
  ever, even after it crossed the floor. With `expires`, a below-floor reject lasts 30 days and
  the candidate re-enters the admission gate afterwards; an unresolved repo 7 days; an archived
  one 90 days. A HUMAN rejection (a PR closed unmerged) carries no `expires`: it is permanent,
  because "never re-propose a human-rejected record" is JR.md law — and a permanent rejection
  can never be overwritten by a TTL'd note (see _write).
- `repo_id` (GitHub's numeric repository id, optional). Stable across renames — the only key that
  still identifies `pr3y/Bruce` after it became `BruceDevices/firmware` (id 795166961). The
  `by_repo_id` view is DERIVED at load time from the records; ledger._save never persists it.
- `evidence_url` (optional). The exact URL the admission decision was made from (a release
  asset, a platformio.ini, a README anchor), kept verbatim so a later reader can re-check it.
- `review` + `history` (optional). An owner-review decision and the records it replaced — see
  record_review_decision and SPEC-jr-review-routing.md §5. Once a record has either, every later
  overwrite appends the replaced record to `history`: nothing is deleted.
- `aliases` (optional). [{id, repo}] other names a decision for this record's `repo_id` arrived
  under (a renamed repo, a re-derived firmware id). One numeric repo_id owns ONE record: a later
  decision under a new name is written to (or, against a protected record, refused by) the record
  that already owns the repo_id, and the new name becomes an alias — see canonical_id.
- status `expired` + `expired_at`. A record whose TTL ran out keeps its history (the original
  `timestamp` is the decision time, `expired_at` is when it lapsed) but is neither blocking nor
  "seen": to every gate it reads as absent. ledger.is_blocked / is_seen already return False
  for it because it is in neither BLOCKING_STATUSES nor "seen".

Everything here takes an injectable `path` (resolved LAZILY to ledger.DEFAULT_LEDGER_PATH, so
the repo's monkeypatch-the-default test pattern reaches this module too) and an injectable
`now` (naive datetimes are treated as UTC) — the same contract as jr/ledger.py.

Contract with the publisher (jr/publish.py): the ledger file is ALWAYS part of a tick's
pathspec — `staged_paths()` returns it — so every decision Jr takes is committed with the change
it explains. Memory is not box-local for the tick: it ships, because the PR is the audit trail.

Known, deliberate: jr/drain.py (the paused legacy lane, deleted in Phase 6) still gates through
ledger.is_blocked/is_seen, which have no clock. A TTL'd rejection therefore blocks that lane
until expire() has rewritten the file; the tick calls expire() first thing, so for the tick the
two views agree. That lane's `ledger.record_seen` (jr/drain.py) also writes TTL-less v1 notes
that drop `expires`/`repo_id`/`evidence_url`; the Phase 3 admission stage writes through
memory.record_seen instead, and the legacy lane is deleted in Phase 6.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ledger
from ledger import load_ledger, _save  # noqa: F401  (memory's writers reload via load_ledger)

REPO = Path(__file__).resolve().parent.parent
LEDGER_RELPATH = str(ledger.DEFAULT_LEDGER_PATH.relative_to(REPO))   # "jr/proposed_ledger.json"

# Default TTLs for time-bounded decisions (PLAN §3.3 admission gates). Days.
SEEN_TTL_DAYS = 30              # scored but skipped; re-check after a month
FLOOR_REJECT_DAYS = 30          # below stars/forks floor; stars move, so re-check
UNRESOLVED_REJECT_DAYS = 7      # GitHub could not resolve the repo (rename, outage, 404)
ARCHIVED_REJECT_DAYS = 90       # archived repos rarely un-archive
NO_BUILD_SIGNAL_DAYS = 60       # no ESP32 build artifact found; repos gain releases slowly

PERMANENT = None                # ttl_days=None → no `expires` → never expires
EXPIRABLE_STATUSES = ("seen", "rejected")   # the only statuses expire() may flip


def _path(path: Path | None) -> Path:
    return ledger.DEFAULT_LEDGER_PATH if path is None else path


def _aware(dt: datetime | None) -> datetime:
    dt = dt or datetime.now(timezone.utc)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return _aware(dt).isoformat()


def _expiry(now: datetime, ttl_days: int | None) -> str | None:
    if ttl_days is None:
        return None
    return _iso(_aware(now) + timedelta(days=ttl_days))


def is_permanent_rejection(record: dict | None) -> bool:
    return bool(record) and record.get("status") == "rejected" and not record.get("expires")


def is_protected(record: dict | None) -> bool:
    """A record no TTL'd decision may replace: a permanent rejection, a merged or proposed one."""
    return is_permanent_rejection(record) or (record or {}).get("status") in ("merged", "proposed")


# --- reading ---------------------------------------------------------------------------------

def _view_rank(rec: dict) -> tuple:
    """How two records sharing a repo_id compete for the by_repo_id view: a protected record (a
    permanent veto, merged, proposed) beats any TTL'd one; between TTL'd records the one that
    expires LATER wins (it is the newer decision), so an expired alias of a renamed repo
    (ji1ore/remotekeyer_wifi -> Wifi_Rig_CW, 2026-11-17) never shadows the live decision whatever
    the records' order in the file. Clock-free: the same file always ranks the same way."""
    exp = _parse(rec.get("expires"))
    return (1 if is_protected(rec) else 0, exp.timestamp() if exp is not None else float("inf"))


def _repo_id_view(led: dict) -> dict:
    """{repo_id: firmware_id} over every record that carries a parsable `repo_id`, by _view_rank."""
    view, rank = {}, {}
    for fid, rec in led["by_id"].items():
        if not isinstance(rec, dict) or rec.get("repo_id") is None:
            continue
        try:
            rid = int(rec["repo_id"])
        except (TypeError, ValueError):
            continue
        r = _view_rank(rec)
        if rid in view and r <= rank[rid]:
            continue
        view[rid], rank[rid] = fid, r
    return view


def load(path: Path | None = None) -> dict:
    """The ledger (jr/ledger.py's shape) plus a DERIVED `by_repo_id` view: {repo_id: firmware_id}
    over every record that carries a `repo_id`. ledger._save strips it, so it can never go stale
    relative to the records. Two records sharing a repo_id (a rename written before canonical_id)
    resolve by _view_rank: the protected one, else the later-expiring one, so a permanent veto is
    never shadowed by a later TTL'd record and a live decision never by an expired alias."""
    led = load_ledger(_path(path))
    led["by_repo_id"] = _repo_id_view(led)
    return led


def is_expired(record: dict, now: datetime | None = None) -> bool:
    """True when the record carries an `expires` that is already in the past. A record with no
    `expires`, or an unparsable one, never expires (permanent decision, or an old v1 record)."""
    exp = _parse(record.get("expires"))
    if exp is None:
        return False
    return exp <= _aware(now)


def lookup(led: dict, firmware_id: str | None = None, repo: str | None = None,
           repo_id: int | None = None) -> dict | None:
    """ledger.lookup plus a third key: GitHub's numeric `repo_id`, which survives renames."""
    rec = ledger.lookup(led, firmware_id=firmware_id, repo=repo)
    if rec is not None:
        return rec
    if repo_id is not None:
        fid = led.get("by_repo_id", {}).get(int(repo_id))
        if fid:
            return led["by_id"].get(fid)
    return None


def canonical_id(led: dict, firmware_id: str | None, repo_id: int | None) -> str | None:
    """The id a decision for (`firmware_id`, `repo_id`) is written under, resolved by the stable
    repo_id BEFORE any record is created: the record owning the repo_id, protected or not; else
    `firmware_id` — or None when `firmware_id`'s record belongs to ANOTHER repo_id (an id
    collision: an unrelated repo's record is never overwritten). `led` must come from load()
    (it reads the derived by_repo_id view, which already prefers a protected owner)."""
    owner = led.get("by_repo_id", {}).get(int(repo_id)) if repo_id is not None else None
    if owner:
        return owner
    held = led["by_id"].get(firmware_id) if firmware_id else None
    if repo_id is not None and (held or {}).get("repo_id") is not None:
        return None
    return firmware_id


def _with_alias(rec: dict, firmware_id: str, repo_key: str) -> list:
    """`rec`'s aliases plus (firmware_id, repo_key) when that is not `rec`'s own identity."""
    aliases = list(rec.get("aliases") or [])
    alias = {"id": firmware_id, "repo": repo_key}
    if (firmware_id, repo_key) != (rec.get("id"), rec.get("repo")) and alias not in aliases:
        aliases.append(alias)
    return aliases


def is_blocked(led: dict, firmware_id: str | None = None, repo: str | None = None,
               repo_id: int | None = None, now: datetime | None = None) -> bool:
    """A blocking record (proposed / rejected) that has NOT expired. An overdue TTL rejection
    stops blocking the moment its `expires` passes, even before expire() has rewritten it —
    so a tick that forgot to expire cannot keep a candidate frozen out."""
    rec = lookup(led, firmware_id=firmware_id, repo=repo, repo_id=repo_id)
    if rec is None or rec.get("status") not in ledger.BLOCKING_STATUSES:
        return False
    return not is_expired(rec, now)


def is_seen(led: dict, firmware_id: str | None = None, repo: str | None = None,
            repo_id: int | None = None, now: datetime | None = None) -> bool:
    """A live (unexpired) `seen` note. Same expiry semantics as is_blocked."""
    rec = lookup(led, firmware_id=firmware_id, repo=repo, repo_id=repo_id)
    if rec is None or rec.get("status") != "seen":
        return False
    return not is_expired(rec, now)


def staged_paths() -> list[str]:
    """The ledger's path relative to the repo root — the publisher stages it on every tick. A
    constant: inside a worktree the file is at the same relative path."""
    return [LEDGER_RELPATH]


# --- writing ---------------------------------------------------------------------------------

def _write(firmware_id: str, repo: str, status: str, reason: str | None, ttl_days: int | None,
           repo_id: int | None, evidence_url: str | None, pr_ref: str | None,
           path: Path | None, now: datetime | None) -> dict:
    """Write one record. THREE RULES. (1) A permanent rejection (a human veto, a deliberate seed)
    is never overwritten by anything but another permanent rejection — not by a TTL'd note, not
    by a new proposal. (2) A `merged` record changes ONLY through reconciliation or a permanent
    rejection — the write-time mirror of scripts/ledger_guard.py's "a merged record changes only
    to a permanent rejection". Every other incoming status is refused: a TTL'd rejection / `seen`
    note (the launcher scan meets catalogued firmware every tick and scores it `already_catalogued`
    — #153 turned four merged records into 30-day rejections) AND a re-`proposed` from the open-PR
    ledger backfill that met an already-merged id (#181: hydrate_open_pr_ledger re-proposes every
    id in an OPEN backfill PR, an illegal merged->proposed downgrade). (3) A `proposed` record is
    not downgraded by a TTL'd rejection or a `seen` note either; only a new proposal (a refresh) or
    a permanent rejection replaces it. A missing repo_id is backfilled on any refusal. Otherwise
    the latest decision is the truth."""
    if not firmware_id and not repo:
        # An unparseable/empty repo has neither an id nor a repo to key the ledger by — persisting
        # it anyway leaves a record under a falsy key, which is corruption, not audit history (a
        # tick once shipped exactly this and scripts/ledger_guard.py refused every PR after with
        # "bad key"). Nothing to transition either, so this is a pure no-op: load and return.
        return load_ledger(_path(path))
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    existing = led["by_id"].get(firmware_id)
    incoming_permanent = status == "rejected" and ttl_days is None
    if is_permanent_rejection(existing) and not incoming_permanent:
        return led
    # A refused write backfills a missing repo_id ONLY from the same repository: a namesake fork's
    # refused decision must never stamp the fork's id on the record that owns the firmware id (2026-11-18).
    same_repo = bool(existing) and _same_repo(existing.get("repo"), repo)
    if existing and existing.get("status") == "merged" and not incoming_permanent:
        if repo_id is not None and existing.get("repo_id") is None and same_repo:
            existing["repo_id"] = int(repo_id)          # by_repo_id is derived at load time
            _save(led, path)
        return led
    if existing and existing.get("status") == "proposed" and (status == "seen" or (status == "rejected" and not incoming_permanent)):
        if repo_id is not None and existing.get("repo_id") is None and same_repo:
            existing["repo_id"] = int(repo_id)          # by_repo_id is derived at load time
            _save(led, path)
        return led
    repo_key = repo.lower()
    rec = {
        "id": firmware_id, "repo": repo_key, "status": status,
        "timestamp": _iso(now), "pr_ref": pr_ref,
    }
    if existing and (existing.get("review") or existing.get("history")):
        rec["history"] = _history(existing)
    if existing and existing.get("aliases"):
        rec["aliases"] = existing["aliases"]
    if reason is not None:
        rec["reason"] = reason
    exp = _expiry(now, ttl_days)
    if exp is not None:
        rec["expires"] = exp
    if repo_id is not None:
        rec["repo_id"] = int(repo_id)
    if evidence_url:
        rec["evidence_url"] = evidence_url
    led["by_id"][firmware_id] = rec
    led["by_repo"][repo_key] = firmware_id
    _save(led, path)
    return led


def _history(existing: dict) -> list:
    """`existing`'s history plus `existing` itself (minus its own history): the decision it
    replaces is kept, never deleted (SPEC-jr-review-routing.md §5)."""
    return list(existing.get("history") or []) + [{k: v for k, v in existing.items() if k != "history"}]


def record_review_decision(firmware_id: str, repo: str, reason: str, *, repo_id: int | None = None,
                           evidence: dict | None = None, evidence_rev: str | None = None,
                           pr_ref: str | None = None, outcome: str = "raised",
                           raised_at: datetime | None = None, ttl_days: int = NO_BUILD_SIGNAL_DAYS,
                           path: Path | None = None, now: datetime | None = None) -> dict:
    """An owner-review decision (SPEC-jr-review-routing.md §5): a TTL'd rejection — `ttl_days`
    from `raised_at` (default `now`), not from whenever it is re-read — carrying a `review` block
    {outcome, pr_ref, raised_at, evidence_rev, evidence}. `outcome`: raised (asked in this tick's
    PR) / open / closed (the owner closed that review PR unmerged). The candidate stays unadmitted.

    Identity is resolved by repo_id first (canonical_id): a decision arriving under a new name for
    a repo_id another record owns goes to THAT record, and the new name is kept as an alias. A
    firmware_id whose record belongs to a different repo_id is an id collision: nothing is written.

    Same refusals as _write: never over a permanent rejection, a merged or a proposed record (a
    missing repo_id is backfilled, a new name aliased). Idempotent: a record that already says the
    same is not rewritten. Otherwise the replaced record is appended to `history`."""
    if not firmware_id and not repo:
        return load_ledger(_path(path))
    path = _path(path)
    raised = _aware(raised_at or now)
    led = load(path)
    repo_key = repo.lower()
    fid = canonical_id(led, firmware_id, repo_id)
    if fid is None:
        return led                                     # an id collision: never overwrite another repo_id
    existing = led["by_id"].get(fid)
    if is_protected(existing):
        return _refuse(led, existing, firmware_id, repo_key, repo_id, path)
    rid = int(repo_id) if repo_id is not None else (existing or {}).get("repo_id")
    review = {"outcome": outcome, "pr_ref": pr_ref, "raised_at": _iso(raised),
              "evidence_rev": evidence_rev, "evidence": evidence}
    renamed = fid != firmware_id
    rec = {"id": fid, "repo": existing.get("repo") or repo_key if renamed else repo_key, "status": "rejected",
           "timestamp": _iso(raised), "pr_ref": None, "reason": reason,
           "expires": _expiry(raised, ttl_days), "review": review}
    if rid is not None:
        rec["repo_id"] = rid
    aliases = _with_alias(existing, firmware_id, repo_key) if renamed else (existing or {}).get("aliases")
    if aliases:
        rec["aliases"] = aliases
    if existing:
        if {k: v for k, v in existing.items() if k != "history"} == rec:
            return led
        rec["history"] = _history(existing)
    led["by_id"][fid] = rec
    for key in (rec["repo"], repo_key):
        holder = led["by_repo"].get(key)
        if holder == fid or not is_protected(led["by_id"].get(holder)):
            led["by_repo"][key] = fid                  # a name never moves off a veto (a legacy one has no repo_id)
    _save(led, path)
    return led


def _same_repo(a, b) -> bool:
    """Two owner/repo strings name the same repository (case and a trailing .git ignored)."""
    norm = lambda r: str(r or "").strip().lower().removesuffix(".git").rstrip("/")  # noqa: E731
    return bool(norm(a)) and norm(a) == norm(b)


def _refuse(led: dict, existing: dict, firmware_id: str, repo_key: str, repo_id: int | None,
            path: Path) -> dict:
    """A protected record is never replaced: backfill a missing repo_id, alias a new name (so a
    lookup by it reaches the veto). Saves only when something changed."""
    changed = False
    # only from the same repository: a namesake fork's decision never stamps its id on the record that owns the
    # firmware id (review of #1855, 2026-11-19 — the same rule as _write's)
    if repo_id is not None and existing.get("repo_id") is None and _same_repo(existing.get("repo"), repo_key):
        existing["repo_id"] = int(repo_id)
        changed = True
    if firmware_id != existing["id"]:
        aliases = _with_alias(existing, firmware_id, repo_key)
        if aliases != (existing.get("aliases") or []):
            existing["aliases"] = aliases
            changed = True
        if led["by_repo"].get(repo_key) != existing["id"]:
            led["by_repo"][repo_key] = existing["id"]
            changed = True
    if changed:
        _save(led, path)
    return led


def record_rejected(firmware_id: str, repo: str, reason: str, ttl_days: int | None = PERMANENT,
                    repo_id: int | None = None, evidence_url: str | None = None,
                    pr_ref: str | None = None, path: Path | None = None,
                    now: datetime | None = None) -> dict:
    """Reject `firmware_id` (from `repo`) with a mandatory `reason`. `ttl_days=None` is a
    PERMANENT rejection (a human closed the PR, a deliberate seed); a number makes it re-check
    after that many days (below floor: FLOOR_REJECT_DAYS, unresolved: UNRESOLVED_REJECT_DAYS,
    archived: ARCHIVED_REJECT_DAYS, no build signal: NO_BUILD_SIGNAL_DAYS)."""
    return _write(firmware_id, repo, "rejected", reason, ttl_days, repo_id, evidence_url,
                  pr_ref, path, now)


def record_seen(firmware_id: str, repo: str, reason: str | None = None,
                ttl_days: int | None = SEEN_TTL_DAYS, repo_id: int | None = None,
                evidence_url: str | None = None, path: Path | None = None,
                now: datetime | None = None) -> dict:
    """A soft, TTL'd note that a candidate was scored and skipped (non-blocking). Default TTL
    SEEN_TTL_DAYS; after it the prefilter fetches and scores the repo again."""
    return _write(firmware_id, repo, "seen", reason, ttl_days, repo_id, evidence_url,
                  None, path, now)


def record_proposed(firmware_id: str, repo: str, pr_ref: str | None = None,
                    repo_id: int | None = None, evidence_url: str | None = None,
                    path: Path | None = None, now: datetime | None = None) -> dict:
    """ledger.record_proposed plus the v2 fields. Never expires: an open PR blocks until a human
    or reconcile_prs() decides it. Refused silently over a permanent rejection."""
    return _write(firmware_id, repo, "proposed", None, PERMANENT, repo_id, evidence_url,
                  pr_ref, path, now)


def _carry_refusal(led: dict, view: dict, fid, rec, now: datetime) -> str | None:
    """Why record `rec` (keyed `fid` in an open tick PR's ledger) is NOT carried, or None to carry it."""
    if not fid or not isinstance(rec, dict) or rec.get("id") != fid:
        return "malformed"
    if rec.get("status") not in EXPIRABLE_STATUSES or not rec.get("expires"):
        return "not a TTL'd decision"          # proposals: hydrate_open_pr_ledger; vetoes: a closed PR or a human
    if rec.get("review"):
        return "owner-review decision"         # review_memory.reconcile owns those
    if is_expired(rec, now):
        return "expired"
    ours = led["by_id"].get(fid)
    if ours == rec:
        return "same"
    if is_protected(ours):
        return "protected"
    if ours is not None and ours.get("review") and ours.get("status") != "expired" and not is_expired(ours, now):
        return "live owner-review decision here"   # review_memory owns it; it is replaced only through _write
    if ours is not None:
        mine, theirs = _parse(ours.get("timestamp")), _parse(rec.get("timestamp"))
        if theirs is None or (mine is not None and _aware(mine) >= _aware(theirs)):
            return "ours is newer"
    rid = rec.get("repo_id")
    try:
        owner = view.get(int(rid)) if rid is not None else None
    except (TypeError, ValueError):
        return "malformed"
    if owner is not None and owner != fid and is_protected(led["by_id"].get(owner)):
        return "repo id held by a protected record"
    return None


def _kept(ours: dict | None, rec: dict) -> dict:
    """`rec` as carried over `ours`, keeping what _write keeps: past a review or history, `ours` and its
    history go first into `history` (then any of `rec`'s own entries not already there); aliases are
    the union, ours first."""
    rec = dict(rec)
    if not ours:
        return rec
    if ours.get("review") or ours.get("history"):
        hist = _history(ours)
        hist += [h for h in rec.get("history") or [] if h not in hist]
        rec["history"] = hist
    aliases = list(ours.get("aliases") or [])
    for alias in rec.get("aliases") or []:         # {"id", "repo"} dicts (_with_alias): union by equality
        if alias not in aliases:
            aliases.append(alias)
    if aliases:
        rec["aliases"] = aliases
    return rec


def carry_decisions(sources, path: Path | None = None, now: datetime | None = None) -> list[tuple[str, str]]:
    """Carry the TTL'd decisions open tick PRs committed into this ledger (SPEC-espatlas-jr.md, memory step).

    A tick starts from origin/main, so a decision another tick recorded in a PR that has not merged — a
    jr-review PR waiting for the owner, or a bookkeeping PR about to be closed as superseded — would be
    paid for again every hour. `sources` is [(pr_ref, by_id)] read from those PRs' committed ledgers,
    oldest first. A record is copied (timestamp, expires, reason, repo_id) only when it is a live `seen` /
    `rejected` decision WITH `expires`, carries no `review` block, and either this ledger lacks it or holds
    an older unprotected one that is not a live owner-review decision. What the older record knew is kept
    as _write keeps it (`_kept`: its history and itself into `history`, aliases unioned). Never over a merged, proposed or permanent record;
    never under a repo id a different protected record owns; by_repo never moves off a protected record.
    Those are memory._write's refusals, so scripts/ledger_guard.py passes by construction.
    Saves once, only when something was carried. Returns [(pr_ref, firmware_id)] carried."""
    now = _aware(now)
    path = _path(path)
    led = load(path)
    carried = _carry_into(led, sources, now)
    if carried:
        _save(led, path)
    return carried


def _with_repo_id_view(led: dict) -> dict:
    """`led` plus the derived by_repo_id view load() builds (same rule: _view_rank)."""
    led["by_repo_id"] = _repo_id_view(led)
    return led


def _carry_into(led: dict, sources, now: datetime) -> list[tuple[str, str]]:
    """carry_decisions on an in-memory ledger (with its by_repo_id view); returns what it carried."""
    carried = []
    for pr_ref, by_id in sources or []:
        if not isinstance(by_id, dict):
            continue
        for fid, rec in by_id.items():
            if _carry_refusal(led, led["by_repo_id"], fid, rec, now) is not None:
                continue
            rec = _kept(led["by_id"].get(fid), rec)
            led["by_id"][fid] = rec
            repo_key = str(rec.get("repo") or fid).lower()
            if not is_protected(led["by_id"].get(led["by_repo"].get(repo_key))):
                led["by_repo"][repo_key] = fid
            if rec.get("repo_id") is not None and not is_protected(led["by_id"].get(led["by_repo_id"].get(int(rec["repo_id"])))):
                led["by_repo_id"][int(rec["repo_id"])] = fid
            carried.append((pr_ref, fid))
    return carried


def merge_pr_ledger(main: dict, base: dict, pr: dict, now: datetime | None = None) -> dict:
    """The ledger a jr-review PR should carry after main moved (SPEC-jr-review-routing.md §8): main's,
    plus every record the PR changed since the merge base under carry_decisions' rules, plus the PR's own
    `proposed` records where main holds nothing newer and nothing protected. Pure: inputs untouched.
    Everything it writes is what carry_decisions or a proposal would, so scripts/ledger_guard.py passes."""
    now = _aware(now)
    led = _with_repo_id_view({"by_id": copy.deepcopy(main.get("by_id") or {}),
                              "by_repo": copy.deepcopy(main.get("by_repo") or {})})
    base_by_id = base.get("by_id") or {}
    changed = {k: v for k, v in (pr.get("by_id") or {}).items() if base_by_id.get(k) != v}
    _carry_into(led, [("pr", changed)], now)
    for fid, rec in sorted(changed.items()):
        if not isinstance(rec, dict) or rec.get("status") != "proposed" or rec.get("id") != fid:
            continue
        ours = led["by_id"].get(fid)
        if ours is not None and (is_protected(ours) or
                                 (_parse(ours.get("timestamp")) or now) > (_parse(rec.get("timestamp")) or now)):
            continue
        led["by_id"][fid] = copy.deepcopy(rec)
        led["by_repo"][str(rec.get("repo") or fid).lower()] = fid
    led.pop("by_repo_id", None)
    return led


def expire(path: Path | None = None, now: datetime | None = None) -> list[str]:
    """Flip every `seen` / `rejected` record whose `expires` has passed to status `expired`
    (history kept: `timestamp` stays the decision time, `expired_at` records the lapse). Never
    touches `proposed` (an open PR is settled by reconcile_prs, not by a clock) or `merged`.
    Returns the ids flipped; writes nothing when nothing changed."""
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    flipped = []
    for fid, rec in led["by_id"].items():
        if rec.get("status") not in EXPIRABLE_STATUSES:
            continue
        if is_expired(rec, now):
            rec["status"] = "expired"
            rec["expired_at"] = _iso(now)
            flipped.append(fid)
    if flipped:
        _save(led, path)
    return flipped


def reconcile_merged(catalogued_ids: set[str], path: Path | None = None,
                     now: datetime | None = None) -> list[str]:
    """Every `proposed` ledger id that now appears in the catalog was merged: flip it. Only
    `proposed` records — a `seen`/`rejected` id that happens to share a slug with a catalogued
    record (e.g. a fork's note under the original's id) must not be relabelled "merged"; that
    is what the by-repo keying and the fork gate are for."""
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    flipped = []
    for fid, rec in led["by_id"].items():
        if rec.get("status") == "proposed" and fid in catalogued_ids:
            rec["status"] = "merged"
            rec["timestamp"] = _iso(now)
            flipped.append(fid)
    if flipped:
        _save(led, path)
    return flipped


REPO_NOTE_PREFIX = "repo-note:"


def repo_note_key(owner_repo: str) -> str:
    """The ledger key that remembers a decision about `owner_repo` when the decision's own record cannot
    hold it (a `merged` record owns the firmware id): a key of its own, never a firmware id, carrying no
    repo_id, so the by_repo_id identity view is untouched."""
    return REPO_NOTE_PREFIX + owner_repo.lower()


def reconcile_catalogued(sources: dict[str, str], path: Path | None = None,
                         now: datetime | None = None, resolve_id=None) -> dict:
    """A catalogued firmware's id belongs to its own source repository (2026-11-18). `sources` maps each
    catalogued firmware id to the owner/repo its firmware.md `url:` names (lowercased). For each:
    - no record → a `merged` record of that source ("added");
    - a TTL'd rejection, `seen`, `expired` or `merged` record of ANOTHER repository (a namesake fork that
      derived the same slug; a fork the catalog was later pointed away from, e.g. sshclient, Sep 2) →
      that record moves, unchanged but for its key and without repo_id, to repo_note_key(<its repo>) so
      the other repository stays decided, and the id gets the `merged` record ("moved"): the reviewed
      catalog record is the authority on whose id this is;
    - a permanent rejection (a human veto) or a `proposed` record (an open PR) of another repository is
      never touched ("kept"; a human or reconcile_prs decides those).
    The source record carries no repo_id: GitHub's id is backfilled by the next same-repo decision.
    Nothing is deleted (scripts/ledger_guard.py: append-only). An empty `sources` does nothing (a tick
    looking at the wrong tree, as reconcile_removed refuses).
    A record that carries a GitHub repo_id is compared BY ID, never by name (2nd review of #1855, 2026-11-19:
    two "namesakes" were the catalogued repository itself under its pre-rename name): `resolve_id(owner/repo)`
    answers GitHub's id for the catalog source. Same id → a rename: the record is updated in place (source
    name, `merged`, id kept, the old name an alias) ("renamed"). Another id → a real namesake, moved as above.
    Unresolvable (no resolver, GitHub silent) → left alone ("kept"): no identity decided on a name.
    Returns {"added", "moved", "renamed", "kept"}."""
    out = {"added": [], "moved": [], "renamed": [], "kept": []}
    if not sources:
        return out
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    for fid, repo in sorted(sources.items()):
        repo = (repo or "").lower()
        if not fid or not repo:
            continue
        rec = led["by_id"].get(fid)
        if rec is not None and _same_repo(rec.get("repo"), repo):
            continue
        if rec is not None and (is_permanent_rejection(rec) or rec.get("status") == "proposed"):
            out["kept"].append(fid)
            continue
        rid = (rec or {}).get("repo_id")
        if rec is not None and type(rid) is int:
            sid = resolve_id(repo) if resolve_id is not None else None
            if type(sid) is not int:
                out["kept"].append(fid)                 # cannot tell rename from namesake: decide nothing
                continue
            if sid == rid:                              # the same repository, renamed upstream
                old = str(rec.get("repo") or "").lower()
                rec.update(repo=repo, status="merged", timestamp=_iso(now),
                           reason="present in the catalog (reconciled from its firmware.md; renamed upstream)")
                rec["aliases"] = _with_alias(rec, fid, old)          # after the update: the old name is an alias
                rec.pop("expires", None)
                led["by_repo"][repo] = fid
                out["renamed"].append(fid)
                continue
        if rec is not None:
            other = str(rec.get("repo") or "").lower()
            key = repo_note_key(other)
            if key not in led["by_id"]:
                note = {k: v for k, v in rec.items() if k != "repo_id"}
                note["id"] = key
                if note.get("status") == "merged":
                    # a note is never `merged`: reconcile_removed would turn a merged record outside the catalog
                    # into a permanent "removed from catalog" veto nobody made (review of #1855, 2026-11-19)
                    note.update(status="rejected", reason=f"namesake of catalogued {fid} (was merged): " + str(rec.get("reason") or ""),
                                expires=_expiry(now, 365))
                led["by_id"][key] = note
            led["by_repo"][other] = key
            out["moved"].append(fid)
        else:
            out["added"].append(fid)
        led["by_id"][fid] = {"id": fid, "repo": repo, "status": "merged", "timestamp": _iso(now), "pr_ref": None,
                             "reason": "present in the catalog (reconciled from its firmware.md)"}
        led["by_repo"][repo] = fid
    if out["added"] or out["moved"] or out["renamed"]:
        _save(led, path)
    return out


def reconcile_removed(catalogued_ids: set[str], path: Path | None = None,
                      now: datetime | None = None,
                      reason: str = "removed from catalog") -> list[str]:
    """A `merged` id that is no longer in the catalog was deleted by a human (or by a guarded
    purge). It becomes a PERMANENT rejection with `reason`, so the tick never re-authors what
    someone took out on purpose. REFUSES to act on an EMPTY catalog: that is a tick looking at
    the wrong tree, not a catalog that lost every record. Returns the ids flipped."""
    if not catalogued_ids:
        return []
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    flipped = []
    for fid, rec in led["by_id"].items():
        if rec.get("status") == "merged" and fid not in catalogued_ids and not fid.startswith(REPO_NOTE_PREFIX):
            rec["status"] = "rejected"
            rec["reason"] = reason
            rec["timestamp"] = _iso(now)
            rec.pop("expires", None)
            flipped.append(fid)
    if flipped:
        _save(led, path)
    return flipped


def reconcile_prs(pr_state, path: Path | None = None,
                  now: datetime | None = None) -> dict:
    """Settle every `proposed` record that has a `pr_ref` by asking `pr_state(pr_ref)` — an
    injectable callable returning "open", "merged" or "closed" (the real one wraps `gh pr view`).
    "closed" (unmerged) is a human veto → PERMANENT rejection; "merged" → merged; "open" or an
    unknown answer → untouched. Returns {"merged": [...], "rejected": [...]}."""
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    out = {"merged": [], "rejected": []}
    for fid, rec in led["by_id"].items():
        if rec.get("status") != "proposed" or not rec.get("pr_ref"):
            continue
        state = pr_state(rec["pr_ref"])
        if state == "merged":
            rec["status"] = "merged"
            rec["timestamp"] = _iso(now)
            rec.pop("expires", None)
            out["merged"].append(fid)
        elif state == "closed":
            rec["status"] = "rejected"
            rec["reason"] = f"PR closed unmerged: {rec['pr_ref']}"
            rec["timestamp"] = _iso(now)
            rec.pop("expires", None)
            out["rejected"].append(fid)
    if out["merged"] or out["rejected"]:
        _save(led, path)
    return out


def gh_pr_state(pr_ref: str, gh=None) -> str:
    """The real `pr_state` for reconcile_prs: `gh pr view <ref> --json state,mergedAt`. Returns
    "open" / "merged" / "closed", or "unknown" on any failure (never raises, never blocks the
    tick). `gh` is injectable (a callable taking argv, returning an object with returncode/stdout)."""
    import json
    import subprocess
    if gh is None:
        def gh(*args):
            return subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True)
    p = gh("pr", "view", pr_ref, "--json", "state,mergedAt")
    if getattr(p, "returncode", 1) != 0:
        return "unknown"
    try:
        d = json.loads(p.stdout)
    except (json.JSONDecodeError, TypeError):
        return "unknown"
    state = (d.get("state") or "").upper()
    if state == "MERGED" or d.get("mergedAt"):
        return "merged"
    if state == "CLOSED":
        return "closed"
    if state == "OPEN":
        return "open"
    return "unknown"
