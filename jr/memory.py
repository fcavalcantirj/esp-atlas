"""EspAtlas Jr — memory v2 (jr/memory.py): the proposed-ledger with time-bounded decisions.

Phase 2 of the rebuild (docs: SPEC-jr-gate-at-ingest.md, JR.md §6 "Memory — what Jr keeps").
This module is the hourly tick's memory. It is a thin, ADDITIVE layer over jr/ledger.py and the
same on-disk file, jr/proposed_ledger.json — it does not fork the ledger, it extends it:

    {"by_id": {"<firmware_id>": {"id", "repo", "status", "timestamp", "pr_ref"
                                [, "reason"] [, "expires"] [, "expired_at"] [, "repo_id"]
                                [, "evidence_url"]}, ...},
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


# --- reading ---------------------------------------------------------------------------------

def load(path: Path | None = None) -> dict:
    """The ledger (jr/ledger.py's shape) plus a DERIVED `by_repo_id` view: {repo_id: firmware_id}
    over every record that carries a `repo_id`. ledger._save strips it, so it can never go stale
    relative to the records."""
    led = load_ledger(_path(path))
    view = {}
    for fid, rec in led["by_id"].items():
        rid = rec.get("repo_id")
        if rid is None:
            continue
        try:
            view[int(rid)] = fid
        except (TypeError, ValueError):
            continue
    led["by_repo_id"] = view
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
    """Write one record. THE ONE RULE: a permanent rejection (a human veto, a deliberate seed)
    is never overwritten by anything but another permanent rejection — not by a TTL'd note, not
    by a new proposal. Otherwise the latest decision is the truth."""
    now = _aware(now)
    path = _path(path)
    led = load_ledger(path)
    existing = led["by_id"].get(firmware_id)
    incoming_permanent = status == "rejected" and ttl_days is None
    if is_permanent_rejection(existing) and not incoming_permanent:
        return led
    repo_key = repo.lower()
    rec = {
        "id": firmware_id, "repo": repo_key, "status": status,
        "timestamp": _iso(now), "pr_ref": pr_ref,
    }
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
        if rec.get("status") == "merged" and fid not in catalogued_ids:
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
