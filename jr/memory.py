"""EspAtlas Jr — memory v2 (jr/memory.py): the proposed-ledger with time-bounded decisions.

Phase 2 of the rebuild (docs: SPEC-jr-gate-at-ingest.md, JR.md §6 "Memory — what Jr keeps").
This module is the hourly tick's memory. It is a thin, ADDITIVE layer over jr/ledger.py and the
same on-disk file, jr/proposed_ledger.json — it does not fork the ledger, it extends it:

    {"by_id": {"<firmware_id>": {"id", "repo", "status", "timestamp", "pr_ref"
                                [, "reason"] [, "expires"] [, "repo_id"] [, "evidence_url"]}, ...},
     "by_repo": {"<owner/repo>": "<firmware_id>", ...}}

What v2 adds, and why each field exists:

- `expires` (ISO-8601 UTC, optional). A rejection or a "seen" note that carries a TTL. The old
  ledger had TTL-less `seen` records: a repo scored below the floor in August stayed skipped for
  ever, even after it crossed the floor. With `expires`, a below-floor reject lasts 30 days and
  the candidate re-enters the admission gate afterwards; an unresolved repo 7 days; an archived
  one 90 days. A HUMAN rejection (a PR closed unmerged) carries no `expires`: it is permanent,
  because "never re-propose a human-rejected record" is JR.md law.
- `repo_id` (GitHub's numeric repository id, optional). Stable across renames — the only key that
  still identifies `pr3y/Bruce` after it became `BruceDevices/firmware` (id 795166961). The
  `by_repo_id` view is DERIVED at load time from the records, never persisted, so it cannot drift.
- `evidence_url` (optional). The exact URL the admission decision was made from (a release
  asset, a platformio.ini, a README anchor), kept verbatim so a later reader can re-check it.
- status `expired`. A record whose TTL ran out keeps its history (a maintainer reading a
  rejection months on can still tell a deliberate decision from a stale artifact) but is
  neither blocking nor "seen": to every gate it reads as absent. ledger.is_blocked / is_seen
  already return False for it because it is in neither BLOCKING_STATUSES nor "seen".

Everything here takes an injectable `path` (default jr/proposed_ledger.json) and an injectable
`now` so tests use tmp_path and fixed clocks — the same contract as jr/ledger.py. Timestamps are
ISO-8601 strings in UTC.

Contract with the publisher (jr/publish.py): the ledger file is ALWAYS part of a tick's
pathspec — `staged_paths()` returns it — so every decision Jr takes is committed with the change
it explains. Memory is not box-local for the tick: it ships, because the PR is the audit trail.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import ledger
from ledger import DEFAULT_LEDGER_PATH, load_ledger, _save  # noqa: F401  (re-exported on purpose)

REPO = Path(__file__).resolve().parent.parent

# Default TTLs for time-bounded decisions (PLAN §3.3 admission gates). Days.
SEEN_TTL_DAYS = 30              # scored but skipped; re-check after a month
FLOOR_REJECT_DAYS = 30          # below stars/forks floor; stars move, so re-check
UNRESOLVED_REJECT_DAYS = 7      # GitHub could not resolve the repo (rename, outage, 404)
ARCHIVED_REJECT_DAYS = 90       # archived repos rarely un-archive
NO_BUILD_SIGNAL_DAYS = 60       # no ESP32 build artifact found; repos gain releases slowly

PERMANENT = None                # ttl_days=None → no `expires` → never expires


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _expiry(now: datetime, ttl_days: int | None) -> str | None:
    if ttl_days is None:
        return None
    return _iso(now + timedelta(days=ttl_days))


# --- reading ---------------------------------------------------------------------------------

def load(path: Path = DEFAULT_LEDGER_PATH) -> dict:
    """The ledger (jr/ledger.py's shape) plus a DERIVED `by_repo_id` view: {repo_id: firmware_id}
    over every record that carries a `repo_id`. Never persisted — recomputed on every load so it
    cannot go stale relative to the records."""
    led = load_ledger(path)
    led["by_repo_id"] = {
        int(rec["repo_id"]): fid
        for fid, rec in led["by_id"].items()
        if rec.get("repo_id") is not None
    }
    return led


def is_expired(record: dict, now: datetime | None = None) -> bool:
    """True when the record carries an `expires` that is already in the past. A record with no
    `expires` never expires (permanent decision, or an old v1 record)."""
    exp = _parse(record.get("expires"))
    if exp is None:
        return False
    return exp <= (now or _utcnow())


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
    if rec is None or rec["status"] not in ledger.BLOCKING_STATUSES:
        return False
    return not is_expired(rec, now)


def is_seen(led: dict, firmware_id: str | None = None, repo: str | None = None,
            repo_id: int | None = None, now: datetime | None = None) -> bool:
    """A live (unexpired) `seen` note. Same expiry semantics as is_blocked."""
    rec = lookup(led, firmware_id=firmware_id, repo=repo, repo_id=repo_id)
    if rec is None or rec["status"] != "seen":
        return False
    return not is_expired(rec, now)


def staged_paths() -> list[str]:
    """The ledger's path relative to the repo root — the publisher stages it on every tick."""
    return [str(DEFAULT_LEDGER_PATH.relative_to(REPO))]


# --- writing ---------------------------------------------------------------------------------

def _write(firmware_id: str, repo: str, status: str, reason: str | None, ttl_days: int | None,
           repo_id: int | None, evidence_url: str | None, pr_ref: str | None,
           path: Path, now: datetime | None) -> dict:
    now = now or _utcnow()
    led = load_ledger(path)
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
                    pr_ref: str | None = None, path: Path = DEFAULT_LEDGER_PATH,
                    now: datetime | None = None) -> dict:
    """Reject `firmware_id` (from `repo`) with a mandatory `reason`. `ttl_days=None` is a
    PERMANENT rejection (a human closed the PR, a deliberate seed); a number makes it re-check
    after that many days (below floor: FLOOR_REJECT_DAYS, unresolved: UNRESOLVED_REJECT_DAYS,
    archived: ARCHIVED_REJECT_DAYS, no build signal: NO_BUILD_SIGNAL_DAYS). Overwrites any prior
    record for the id: the latest decision is the truth."""
    return _write(firmware_id, repo, "rejected", reason, ttl_days, repo_id, evidence_url,
                  pr_ref, path, now)


def record_seen(firmware_id: str, repo: str, reason: str | None = None,
                ttl_days: int | None = SEEN_TTL_DAYS, repo_id: int | None = None,
                evidence_url: str | None = None, path: Path = DEFAULT_LEDGER_PATH,
                now: datetime | None = None) -> dict:
    """A soft, TTL'd note that a candidate was scored and skipped (non-blocking). Default TTL
    SEEN_TTL_DAYS; after it the prefilter fetches and scores the repo again."""
    return _write(firmware_id, repo, "seen", reason, ttl_days, repo_id, evidence_url,
                  None, path, now)


def record_proposed(firmware_id: str, repo: str, pr_ref: str | None = None,
                    repo_id: int | None = None, evidence_url: str | None = None,
                    path: Path = DEFAULT_LEDGER_PATH, now: datetime | None = None) -> dict:
    """ledger.record_proposed plus the v2 fields. Never expires: an open PR blocks until a human
    or reconcile_prs() decides it."""
    return _write(firmware_id, repo, "proposed", None, PERMANENT, repo_id, evidence_url,
                  pr_ref, path, now)


def expire(path: Path = DEFAULT_LEDGER_PATH, now: datetime | None = None) -> list[str]:
    """Flip every record whose `expires` has passed to status `expired` (history kept, no longer
    blocking or seen). Returns the ids flipped; writes nothing when nothing changed."""
    now = now or _utcnow()
    led = load_ledger(path)
    flipped = []
    for fid, rec in led["by_id"].items():
        if rec.get("status") in ("expired", "merged"):
            continue
        if is_expired(rec, now):
            rec["status"] = "expired"
            rec["timestamp"] = _iso(now)
            flipped.append(fid)
    if flipped:
        _save(led, path)
    return flipped


def reconcile_merged(catalogued_ids: set[str], path: Path = DEFAULT_LEDGER_PATH,
                     now: datetime | None = None) -> list[str]:
    """ledger.reconcile_merged: every ledger id now in the catalog becomes `merged`."""
    return ledger.reconcile_merged(catalogued_ids, path=path,
                                   now=_iso(now) if now else None)


def reconcile_removed(catalogued_ids: set[str], path: Path = DEFAULT_LEDGER_PATH,
                      now: datetime | None = None,
                      reason: str = "removed from catalog") -> list[str]:
    """A `merged` id that is no longer in the catalog was deleted by a human (or by a guarded
    purge). It becomes a PERMANENT rejection with `reason`, so the tick never re-authors what
    someone took out on purpose. Returns the ids flipped."""
    now = now or _utcnow()
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


def reconcile_prs(pr_state, path: Path = DEFAULT_LEDGER_PATH,
                  now: datetime | None = None) -> dict:
    """Settle every `proposed` record that has a `pr_ref` by asking `pr_state(pr_ref)` — an
    injectable callable returning "open", "merged" or "closed" (the real one wraps `gh pr view`).
    "closed" (unmerged) is a human veto → PERMANENT rejection; "merged" → merged; "open" or an
    unknown answer → untouched. Returns {"merged": [...], "rejected": [...]}."""
    now = now or _utcnow()
    led = load_ledger(path)
    out = {"merged": [], "rejected": []}
    for fid, rec in led["by_id"].items():
        if rec.get("status") != "proposed" or not rec.get("pr_ref"):
            continue
        state = pr_state(rec["pr_ref"])
        if state == "merged":
            rec["status"] = "merged"
            rec["timestamp"] = _iso(now)
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
