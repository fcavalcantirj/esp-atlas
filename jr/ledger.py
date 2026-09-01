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
    {"by_id": {"<firmware_id>": {"id", "repo", "status", "timestamp", "pr_ref"}, ...},
     "by_repo": {"<owner/repo>": "<firmware_id>", ...}}
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

STATUSES = ("proposed", "merged", "rejected")
# statuses that must stop the drain from re-authoring: an open PR (proposed) or a PR a human
# already closed unmerged (rejected). "merged" is NOT here — a merged id is already in the real
# atlas, where catalogued_repos/catalogued_tokens dedup covers it as it always has (drain.py's
# prefilter/scorer gates), so the ledger never needs to duplicate that check.
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
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True))


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
                  pr_ref: str | None = None, now: str | None = None) -> dict:
    """Transition an EXISTING ledger record to `status` (merged/rejected), refreshing its
    timestamp and, if given, its pr_ref. A no-op (ledger returned unchanged, nothing written) if
    `firmware_id` isn't in the ledger yet — there's nothing to transition."""
    if status not in STATUSES:
        raise ValueError(f"unknown ledger status: {status!r} (expected one of {STATUSES})")
    ledger = load_ledger(path)
    record = ledger["by_id"].get(firmware_id)
    if record is None:
        return ledger
    record["status"] = status
    record["timestamp"] = now or _utcnow()
    if pr_ref is not None:
        record["pr_ref"] = pr_ref
    _save(ledger, path)
    return ledger


def mark_rejected(firmware_id: str, path: Path = DEFAULT_LEDGER_PATH, now: str | None = None) -> dict:
    """Mark `firmware_id` rejected — for when a human closes its PR unmerged (deliverable 4).
    A no-op if the id was never proposed (nothing to reject)."""
    return update_status(firmware_id, "rejected", path=path, now=now)


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
