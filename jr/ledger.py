"""EspAtlas Jr — the proposed-ledger (jr/ledger.py).

Prerequisite for running the catalog drain (jr/drain.py) frequently: without this, every run
would re-fetch, re-score, and re-author the SAME firmware while its PR from the last run is
still open (or worse, re-propose one a human already closed unmerged). This ledger is the
persistent memory that stops that — a JSON file at jr/proposed_ledger.json recording, per
firmware id AND per repo owner/repo, the outcome of every id Jr has ever proposed.

Distinct from tools.py's older `_LEDGER`/proposed.json (a flat set of repo names used by the
LLM-driven agent.py/run.py path via `uncatalogued_with_code()`): this module is richer (a status
enum, a timestamp, an optional PR reference, dual id/repo lookup) and is wired into the
deterministic drain path only (drain.py/drain_pr.py). Neither replaces the other.

On-disk shape:
    {"by_id": {"<firmware_id>": {"id", "repo", "status", "timestamp", "pr_ref"[, "reason"]}, ...},
     "by_repo": {"<owner/repo>": "<firmware_id>", ...}}
`reason` is OPTIONAL and additive: a short human string saying WHY a record holds its status
("duplicate_of bruce (repo_id 795166961)", "below floor: 10 stars / 0 forks"). Older records
simply lack the key, and nothing reads it as a gate -- it exists so a human, or a later
maintainer reading a rejection months on, can tell a deliberate decision from a stale artifact.
Two indices over the same records so a caller can dedup-check by either key — mirrors the
catalogued_repos/catalogued_tokens dual-check drain.py's prefilter already does against the real
atlas. `status` is one of proposed/merged/rejected (STATUSES below).

Every function takes an injectable `path` (default DEFAULT_LEDGER_PATH, the real
jr/proposed_ledger.json) so tests read/write a tmp_path file and never the real one, and an
injectable `now` (ISO-8601 string; default real UTC now) so timestamp assertions are deterministic.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent / "proposed_ledger.json"

STATUSES = ("proposed", "merged", "rejected", "seen", "expired")
# "expired" (memory.py, Phase 2): a TTL'd rejection or seen-note whose `expires` passed. History
# is kept, but the record is neither blocking nor seen — every gate reads it as absent.
# statuses that must stop the drain from re-authoring: an open PR (proposed) or a PR a human
# already closed unmerged (rejected). "merged" is NOT here — a merged id is already in the real
# atlas, where catalogued_repos/catalogued_tokens dedup covers it as it always has (drain.py's
# prefilter/scorer gates), so the ledger never needs to duplicate that check.
# "seen" is NON-blocking too (below): it's a soft note that a candidate was scored but skipped for
# being below the popularity floor (SPEC-firmware-floor.md) so the drain's prefilter can skip
# re-fetching it every run, without ever counting as a proposed/rejected PR outcome.
BLOCKING_STATUSES = ("proposed", "rejected")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty() -> dict:
    return {"by_id": {}, "by_repo": {}}


def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> dict:
    """Load the ledger from `path`. A missing file, or one that fails to parse, is an empty
    ledger — never an error (a first-ever drain run has no ledger yet)."""
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("by_id", {})
    data.setdefault("by_repo", {})
    return data


def _save(ledger: dict, path: Path) -> None:
    # `by_repo_id` is a DERIVED view memory.load() adds; it is never persisted. Trailing newline so
    # the file stays byte-identical to the committed one (no spurious "no newline" hunk).
    data = {k: v for k, v in ledger.items() if k != "by_repo_id"}
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def lookup(ledger: dict, firmware_id: str | None = None, repo: str | None = None) -> dict | None:
    """The ledger record for `firmware_id` or `repo` (owner/repo, case-insensitive), id checked
    first — or None if neither is present. A candidate normally only has a repo at prefilter time
    (before the id is derived from a live GitHub fetch) and both once scored."""
    if firmware_id:
        record = ledger["by_id"].get(firmware_id)
        if record:
            return record
    if repo:
        via_repo = ledger["by_repo"].get(repo.lower())
        if via_repo:
            return ledger["by_id"].get(via_repo)
    return None


def is_blocked(ledger: dict, firmware_id: str | None = None, repo: str | None = None) -> bool:
    """True if `firmware_id` or `repo` is in the ledger with a BLOCKING_STATUSES status — the
    drain's dedup gate (deliverable 3): an already-proposed (open PR) or already-rejected
    candidate must not be re-authored on the next run."""
    record = lookup(ledger, firmware_id=firmware_id, repo=repo)
    return record is not None and record["status"] in BLOCKING_STATUSES


def is_seen(ledger: dict, firmware_id: str | None = None, repo: str | None = None) -> bool:
    """True if `firmware_id` or `repo` is in the ledger with status "seen" — a candidate the drain
    already scored and skipped for being below the popularity floor (SPEC-firmware-floor.md).
    Used by drain.prefilter to avoid re-fetching a sub-floor repo on every run. Non-blocking: a
    "seen" record is a soft note, not a proposed/rejected PR outcome."""
    record = lookup(ledger, firmware_id=firmware_id, repo=repo)
    return record is not None and record["status"] == "seen"


def record_seen(firmware_id: str, repo: str, path: Path = DEFAULT_LEDGER_PATH,
                now: str | None = None) -> dict:
    """Record `firmware_id` (from repo owner/repo `repo`) as status=seen — a candidate the drain
    scored but skipped for being below the popularity floor (SPEC-firmware-floor.md). Dual-indexed
    like record_proposed so prefilter can skip it by repo before any GitHub fetch next run, so
    sub-floor filler isn't re-fetched every run. Overwrites any prior record for the same id.
    Returns the updated ledger."""
    ledger = load_ledger(path)
    repo_key = repo.lower()
    ledger["by_id"][firmware_id] = {
        "id": firmware_id, "repo": repo_key, "status": "seen",
        "timestamp": now or _utcnow(), "pr_ref": None,
    }
    ledger["by_repo"][repo_key] = firmware_id
    _save(ledger, path)
    return ledger


def record_proposed(firmware_id: str, repo: str, pr_ref: str | None = None,
                    path: Path = DEFAULT_LEDGER_PATH, now: str | None = None) -> dict:
    """Record `firmware_id` (from repo owner/repo `repo`) as status=proposed, with `pr_ref` (the
    PR URL) if given — called by drain_pr.py at the moment it opens the PR (deliverable 2).
    Overwrites any prior record for the same id: a fresh authoring is always the latest truth.
    Returns the updated ledger."""
    ledger = load_ledger(path)
    repo_key = repo.lower()
    ledger["by_id"][firmware_id] = {
        "id": firmware_id, "repo": repo_key, "status": "proposed",
        "timestamp": now or _utcnow(), "pr_ref": pr_ref,
    }
    ledger["by_repo"][repo_key] = firmware_id
    _save(ledger, path)
    return ledger


def update_status(firmware_id: str, status: str, path: Path = DEFAULT_LEDGER_PATH,
                  pr_ref: str | None = None, now: str | None = None,
                  reason: str | None = None) -> dict:
    """Transition an EXISTING ledger record to `status` (merged/rejected), refreshing its
    timestamp and, if given, its pr_ref and `reason`. A no-op (ledger returned unchanged, nothing
    written) if `firmware_id` isn't in the ledger yet — there's nothing to transition."""
    if status not in STATUSES:
        raise ValueError(f"unknown ledger status: {status!r} (expected one of {STATUSES})")
    ledger = load_ledger(path)
    record = ledger["by_id"].get(firmware_id)
    if record is None:
        return ledger
    record["status"] = status
    record["timestamp"] = now or _utcnow()
    # A v1 transition is a decision without a TTL: a human veto (mark_rejected) or a merge must
    # never inherit an `expires` left by an earlier memory.py TTL'd note, or memory.expire() would
    # later flip the veto to "expired" and Jr could re-propose it.
    record.pop("expires", None)
    if pr_ref is not None:
        record["pr_ref"] = pr_ref
    if reason is not None:
        record["reason"] = reason
    _save(ledger, path)
    return ledger


def mark_rejected(firmware_id: str, path: Path = DEFAULT_LEDGER_PATH, now: str | None = None,
                  reason: str | None = None) -> dict:
    """Mark `firmware_id` rejected — for when a human closes its PR unmerged (deliverable 4), or
    when a deliberate seed rules it out. `reason` records WHY, so a later reader can tell a
    decision from an accident. A no-op if the id was never proposed (nothing to reject)."""
    return update_status(firmware_id, "rejected", path=path, now=now, reason=reason)


def reconcile_merged(catalogued_ids: set[str], path: Path = DEFAULT_LEDGER_PATH,
                     now: str | None = None) -> list[str]:
    """Mark every ledger id that now appears in `catalogued_ids` (the real atlas's
    tools.catalogued_firmware_ids()) as merged (deliverable 4) — a human merged its PR since it
    was proposed. Returns the ids just transitioned; a no-op write (file untouched) when nothing
    changed."""
    ledger = load_ledger(path)
    transitioned = []
    for firmware_id, record in ledger["by_id"].items():
        if firmware_id in catalogued_ids and record["status"] != "merged":
            record["status"] = "merged"
            record["timestamp"] = now or _utcnow()
            transitioned.append(firmware_id)
    if transitioned:
        _save(ledger, path)
    return transitioned
