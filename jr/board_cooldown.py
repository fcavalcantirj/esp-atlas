"""EspAtlas Jr — board backfill cooldown (G3a c): a board on which every source failed is not
retried for COOLDOWN_DAYS, so the hourly Track-A budget moves to boards that can still be filled.

Persisted the way Jr's other decisions are (jr/memory.py): a committed JSON file in jr/ whose
records carry an ISO-8601 UTC `timestamp` and `expires`, shipped in the tick's pathspec so the
decision travels with the PR that explains it. One record per board:

    {"by_board": {"<board_id>": {"board", "reason", "field_reasons", "timestamp", "expires"}}}

A record whose `expires` has passed no longer blocks; save() drops it. Naive datetimes are UTC.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

RELPATH = "jr/board_cooldown.json"
COOLDOWN_DAYS = 7


def _aware(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _expires(record: dict) -> datetime | None:
    try:
        return _aware(datetime.fromisoformat(str(record.get("expires"))))
    except (TypeError, ValueError):
        return None


def load(path: Path) -> dict:
    """The store at `path`; empty when the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"by_board": {}}
    by_board = data.get("by_board") if isinstance(data, dict) else None
    return {"by_board": by_board if isinstance(by_board, dict) else {}}


def is_cooling(store: dict, board_id: str, now: datetime | None = None) -> bool:
    record = store["by_board"].get(board_id)
    if not isinstance(record, dict):
        return False
    expires = _expires(record)
    return expires is not None and _aware(now) < expires


def record(store: dict, board_id: str, reason: str, field_reasons: dict,
           now: datetime | None = None) -> None:
    now = _aware(now)
    store["by_board"][board_id] = {
        "board": board_id, "reason": reason, "field_reasons": field_reasons or {},
        "timestamp": now.isoformat(),
        "expires": (now + timedelta(days=COOLDOWN_DAYS)).isoformat(),
    }


def save(store: dict, path: Path, now: datetime | None = None) -> None:
    """Write the store, dropping records that have already expired, with stable key order."""
    live = {b: r for b, r in sorted(store["by_board"].items()) if is_cooling(store, b, now)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"by_board": live}, indent=2, sort_keys=True) + "\n")
