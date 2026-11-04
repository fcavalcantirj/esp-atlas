"""EspAtlas Jr — risk-based review routing (jr/review_routing.py, SPEC-jr-review-routing.md).

ONE question, one place: may this tick PR auto-merge, or must the owner review it? `classify`
answers it from the STAGED diff (what will actually be committed, not what a stage claims) and the
stage results. A `review` route withholds auto-merge and labels the PR `jr-review`; jr/tick.py's
preflight then knows the PR is waiting on purpose and never treats it as stuck.

The AUTO list is closed and short — bookkeeping, telemetry/demand/signals snapshots, and a
star/date refresh of an existing record. Everything else is REVIEW, because when unsure, a human
looks: a new firmware entry, any recipe (a compatibility claim), a board's flashing fields, a
device-evidence needs_review item, a stage asking for a human, and anything this module does not
recognise — including a diff it cannot read.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import yaml

REVIEW, AUTO = "review", "auto"
REVIEW_LABEL = "jr-review"
REVIEW_LABEL_COLOR = "FBCA04"
REVIEW_LABEL_DESCRIPTION = "Jr: higher-risk change, the owner reviews it (auto-merge withheld)"
MAX_OPEN_REVIEW_PRS = 10

BOOKKEEPING_FILES = ("jr/proposed_ledger.json", "jr/board_cooldown.json")
BOOKKEEPING_DIRS = ("docs/telemetry/",)
SNAPSHOT_DIRS = ("docs/demand/",)
SIGNALS_NAME = "signals.json"
FLASHING_BOARD_FIELDS = ("usb", "usb_serial", "download_mode", "first_flash_notes", "flash_mb")
REFRESH_KEYS = ("popularity",)          # stars / forks / as_of
REFRESH_SOURCE_KEYS = ("verified",)     # a re-verified citation date


@dataclass(frozen=True)
class Change:
    """One staged path. `old`/`new` are the HEAD and index text of a modified record (None when
    not read); only a modified data/**.md record needs them."""
    path: str
    status: str
    old: str | None = None
    new: str | None = None


@dataclass
class Route:
    route: str
    reasons: list = field(default_factory=list)

    @property
    def review(self) -> bool:
        return self.route == REVIEW


def is_bookkeeping(path: str) -> bool:
    return path in BOOKKEEPING_FILES or path.startswith(BOOKKEEPING_DIRS)


def has_review_label(pr: dict) -> bool:
    """True when a gh PR dict carries the jr-review label (case-insensitive). Robust to labels
    being missing / null and to malformed entries, like publish._is_veto."""
    return any(isinstance(lab, dict) and (lab.get("name") or "").lower() == REVIEW_LABEL
               for lab in pr.get("labels") or [])


def _is_signals(path: str) -> bool:
    parts = path.split("/")
    return len(parts) == 4 and parts[:2] == ["data", "firmware"] and parts[3] == SIGNALS_NAME


def _parse(text: str | None) -> tuple[dict, str] | None:
    """(frontmatter, body) of a record, or None when it is not a readable frontmatter document."""
    if not text or not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return (fm, parts[2].strip()) if isinstance(fm, dict) else None


def _without_refresh(fm: dict) -> dict:
    out = {k: copy.deepcopy(v) for k, v in fm.items() if k not in REFRESH_KEYS}
    if isinstance(out.get("sources"), list):
        out["sources"] = [{k: v for k, v in s.items() if k not in REFRESH_SOURCE_KEYS} if isinstance(s, dict) else s
                          for s in out["sources"]]
    return out


def _record_edit_reason(change: Change) -> str | None:
    """None for a star/date refresh of an existing record; otherwise why it needs review."""
    old, new = _parse(change.old), _parse(change.new)
    if old is None or new is None:
        return f"unreadable record diff: {change.path}"
    (old_fm, old_body), (new_fm, new_body) = old, new
    a, b = _without_refresh(old_fm), _without_refresh(new_fm)
    changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    if change.path.startswith("data/boards/"):
        flashing = [k for k in changed if k in FLASHING_BOARD_FIELDS]
        if flashing:
            return f"board flashing field(s) {', '.join(flashing)} changed: {change.path}"
    if changed:
        return f"record content changed ({', '.join(changed)}): {change.path}"
    if old_body != new_body:
        return f"record body changed: {change.path}"
    return None


def _change_reason(change: Change) -> str | None:
    """None when the change is on the AUTO list; otherwise the reason it goes to review."""
    path, status = change.path, change.status[:1]
    if is_bookkeeping(path) or path.startswith(SNAPSHOT_DIRS):
        return None
    if _is_signals(path) and status in ("A", "M"):
        return None
    if status == "D":
        return f"deletion: {path}"
    if path.startswith("data/recipes/"):
        return f"recipe (compatibility claim) {'added' if status == 'A' else 'changed'}: {path}"
    if path.startswith("data/firmware/") and status == "A":
        return f"new firmware entry: {path}"
    if path.startswith("data/") and path.endswith(".md") and status == "M":
        return _record_edit_reason(change)
    return f"not on the low-risk list ({status or '?'}): {path}"


def _stage_reasons(stages) -> list[str]:
    out = []
    for s in stages or ():
        if s.get("needs_human"):
            out.append(f"stage {s.get('name', 'stage')} asked for a human")
        for it in s.get("review") or ():
            out.append(f"device-evidence needs_review: {it.get('repo') or it.get('id')}")
    return out


def classify(changes, stages=(), needs_human: bool = False) -> Route:
    """REVIEW or AUTO for one tick PR: `changes` is the staged diff (list of Change), `stages` the
    tick's stage-result dicts (`needs_human`, `review`). Every reason that forced review is kept, so
    the report can say why. An empty diff is REVIEW: something was staged and we cannot see what."""
    reasons = [] if changes else ["staged diff unreadable or empty"]
    reasons += [r for r in (_change_reason(c) for c in changes) if r]
    reasons += _stage_reasons(stages)
    if needs_human:
        reasons.append("needs_human set by the caller")
    return Route(REVIEW if reasons else AUTO, reasons)
