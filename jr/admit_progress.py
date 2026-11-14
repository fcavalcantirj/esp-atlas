"""EspAtlas Jr — the admit stall alarm (SPEC-espatlas-jr.md, "the backlog queue").

Admit's launcher backlog (jr/stage_admit.py: the undecided repos, counted with zero calls) must
shrink while it is not empty. From 2026-11-12 to 2026-11-14 every tick read "admitted 0 · stopped
before brucedevices/firmware" and nobody was told for days. This module remembers the backlog
size between ticks and says so when it stops shrinking:

- `STALL_AFTER` consecutive ticks without a smaller backlog (equal or larger) -> one Telegram
  nudge, then at most one per UTC day while it stays stuck;
- the first tick with a smaller backlog, or an empty one, clears the streak;
- a dry run reads nothing and writes nothing;
- an unreadable state file is said out loud (a nudge) and replaced, never silent;
- `watch` never raises: the tick goes on whatever happens here.

State is runner-local (outside the repo, which is public), one JSON file, every load-modify-save
under an exclusive flock and replaced atomically: the pattern of jr/ci_watch.Store.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "espatlas-jr" / "admit-progress.json"
STALL_AFTER = 3


def _utc_day(stamp: str) -> str:
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d")


class Store:
    def __init__(self, path: Path = DEFAULT_STATE):
        self.path = Path(path)

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _save(self, data: dict) -> None:
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def observe(self, backlog: int, where: str, now: str) -> list[str]:
        """Record this tick's backlog; return the nudges it earns (usually none)."""
        nudges: list[str] = []
        with self._locked():
            data = None
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text())
                    if not isinstance(data, dict):
                        raise ValueError("not an object")
                except (OSError, ValueError) as e:
                    nudges.append(f"⚠ Jr admit progress state was unreadable ({str(e)[:80]}); "
                                  f"started over at backlog {backlog}.")
                    data = None
            if data is None or backlog <= 0 or backlog < int(data.get("backlog", backlog + 1)):
                data = {"backlog": backlog, "flat": 0, "since": now, "nudged_day": "", "where": where}
            else:
                data.update(backlog=backlog, flat=int(data.get("flat", 0)) + 1, where=where)
                day = _utc_day(now)
                if data["flat"] >= STALL_AFTER and data.get("nudged_day") != day:
                    data["nudged_day"] = day
                    nudges.append(f"⚠ Jr admit stalled: backlog {backlog} undecided, not shrinking for "
                                  f"{data['flat']} ticks since {data.get('since')}. Last: {where[:160]}")
            self._save(data)
        return nudges


def watch(store: Store, backlog: int, where: str, now: str, dry_run: bool = False) -> dict:
    """The tick's entry point. Never raises."""
    if dry_run:
        return {"status": "dry_run", "backlog": backlog, "nudges": []}
    try:
        return {"status": "ok", "backlog": backlog, "nudges": store.observe(int(backlog), where or "", now)}
    except Exception as e:  # noqa: BLE001 — the alarm must never break the tick
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:160], "backlog": backlog, "nudges": []}
