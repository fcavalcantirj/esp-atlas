"""EspAtlas Jr — the committed steering constants (jr/steering.py, SPEC-data-completion.md "Yield").

Every number that decides how Jr splits an hour lives in `jr/steering.json`, read at tick start, so a
change of pace is a reviewed one-line PR and never a code edit. Fail closed to the defaults below: a
missing, unparsable or partly invalid file steers exactly like the constants, and the tick reports why.
"""
from __future__ import annotations

import json
from pathlib import Path

RELPATH = "jr/steering.json"

DEFAULTS = {
    "version": 1,
    "hourly_units": 6,
    "yield": {"window_ticks": 24, "floor_units": 1, "stall_ticks": 24, "topics_stall_ticks": 48},
    "delegate_runs_per_day": 2,
}


def _pos_int(value, default: int) -> tuple[int, str | None]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default, f"{value!r} is not a positive integer"
    return value, None


def load(root: Path) -> tuple[dict, list[str]]:
    """(steering, warnings): the file's values where valid, the defaults elsewhere."""
    out = json.loads(json.dumps(DEFAULTS))
    path = Path(root) / RELPATH
    if not path.is_file():
        return out, [f"{RELPATH} missing: steering defaults"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return out, [f"{RELPATH} unreadable ({type(e).__name__}): steering defaults"]
    if not isinstance(doc, dict):
        return out, [f"{RELPATH} is not an object: steering defaults"]
    warnings: list[str] = []
    for key in ("hourly_units", "delegate_runs_per_day"):
        if key in doc:
            out[key], why = _pos_int(doc[key], DEFAULTS[key])
            if why:
                warnings.append(f"{RELPATH}: {key} {why}; default {DEFAULTS[key]}")
    y = doc.get("yield")
    if y is not None:
        if not isinstance(y, dict):
            warnings.append(f"{RELPATH}: yield is not an object; defaults")
        else:
            for key, default in DEFAULTS["yield"].items():
                if key in y:
                    out["yield"][key], why = _pos_int(y[key], default)
                    if why:
                        warnings.append(f"{RELPATH}: yield.{key} {why}; default {default}")
    return out, warnings
