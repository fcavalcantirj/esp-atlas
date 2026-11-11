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
from datetime import date

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
SELF_CORRECTION_AUTHOR = "jr-self-correction"
SELF_CORRECTION_CLASSES = {"carrier_product": "module_board_id_under_product_build",
                           "generic_base": "devkit_board_id_under_product_build"}
MAX_SELF_CORRECTIONS = 3                # recipes one tick may retract without a person
GITHUB_POPULARITY_KEYS = frozenset({"stars", "forks", "github_repo_id", "github_as_of", "as_of"})
GITHUB_SOURCE_FIELDS = frozenset({
    "popularity.stars", "popularity.forks", "popularity.github_repo_id", "popularity.github_as_of",
})


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


def _firmware_refresh_reason(old_fm: dict, new_fm: dict, old_body: str, new_body: str, path: str) -> str | None:
    """AUTO only for a cited GitHub count/date refresh of one existing firmware."""
    if old_body != new_body:
        return f"record body changed: {path}"
    old_other = {k: v for k, v in old_fm.items() if k not in ("popularity", "sources")}
    new_other = {k: v for k, v in new_fm.items() if k not in ("popularity", "sources")}
    if old_other != new_other:
        return f"record content changed beyond popularity: {path}"
    old_pop, new_pop = old_fm.get("popularity"), new_fm.get("popularity")
    if not isinstance(old_pop, dict) or not isinstance(new_pop, dict):
        return f"unreadable popularity refresh: {path}"
    old_qualifiers = {k: v for k, v in old_pop.items() if k not in GITHUB_POPULARITY_KEYS}
    new_qualifiers = {k: v for k, v in new_pop.items() if k not in GITHUB_POPULARITY_KEYS}
    if old_qualifiers != new_qualifiers:
        return f"non-GitHub popularity changed: {path}"
    if any(k in old_pop and k not in new_pop for k in ("stars", "forks", "github_repo_id", "github_as_of")):
        return f"GitHub popularity field removed: {path}"
    for key in ("stars", "forks"):
        if key in new_pop and (type(new_pop[key]) is not int or new_pop[key] < 0):
            return f"invalid GitHub count: {path}"
    repo_id = new_pop.get("github_repo_id")
    if repo_id is not None and (type(repo_id) is not int or repo_id <= 0 or
                                (old_pop.get("github_repo_id") is not None and old_pop["github_repo_id"] != repo_id)):
        return f"GitHub repository identity changed: {path}"
    if ("downloads" in new_pop or "editorial_home" in new_pop) and old_pop.get("as_of") != new_pop.get("as_of"):
        return f"mixed-signal date changed: {path}"

    url = new_fm.get("url")
    old_sources, new_sources = old_fm.get("sources"), new_fm.get("sources")
    if not isinstance(url, str) or not isinstance(old_sources, list) or not isinstance(new_sources, list):
        return f"unreadable popularity sources: {path}"
    if not all(isinstance(s, dict) for s in old_sources + new_sources):
        return f"unreadable popularity sources: {path}"
    old_base = [s for s in old_sources if s.get("field") not in GITHUB_SOURCE_FIELDS]
    new_base = [s for s in new_sources if s.get("field") not in GITHUB_SOURCE_FIELDS]
    if len(old_base) != len(new_base):
        return f"non-GitHub source changed: {path}"
    for before, after in zip(old_base, new_base):
        if before == after:
            continue
        # Legacy `field: popularity` source may have its verification date
        # advanced with an old-style count refresh, but no URL or field edit.
        if (before.get("field") != "popularity" or before.get("url") != url or
                {k: v for k, v in before.items() if k != "verified"} !=
                {k: v for k, v in after.items() if k != "verified"} or
                after.get("verified") != new_pop.get("as_of")):
            return f"non-GitHub source changed: {path}"
    old_github = [s for s in old_sources if s.get("field") in GITHUB_SOURCE_FIELDS]
    new_github = [s for s in new_sources if s.get("field") in GITHUB_SOURCE_FIELDS]
    old_fields = [s.get("field") for s in old_github]
    new_fields = [s.get("field") for s in new_github]
    if len(set(old_fields)) != len(old_fields) or len(set(new_fields)) != len(new_fields):
        return f"duplicate GitHub source: {path}"
    if not set(old_fields) <= set(new_fields):
        return f"GitHub source removed: {path}"
    if any(s.get("url") != url for s in old_github + new_github):
        return f"GitHub source URL changed: {path}"
    observed = new_pop.get("github_as_of")
    try:
        observed_day = date.fromisoformat(observed[:10]) if isinstance(observed, str) else None
    except ValueError:
        return f"invalid GitHub observation date: {path}"
    if observed is not None or repo_id is not None or new_github:
        expected = {f"popularity.{key}" for key in ("stars", "forks", "github_repo_id", "github_as_of")
                    if key in new_pop}
        if observed_day is None or repo_id is None or set(new_fields) != expected or any(
                s.get("verified") != observed_day.isoformat() for s in new_github):
            return f"GitHub source/date mismatch: {path}"
    if observed is not None and repo_id is None:
        return f"GitHub observation missing stable identity: {path}"
    return None


def _record_edit_reason(change: Change) -> str | None:
    """None for a star/date refresh of an existing record; otherwise why it needs review."""
    old, new = _parse(change.old), _parse(change.new)
    if old is None or new is None:
        return f"unreadable record diff: {change.path}"
    (old_fm, old_body), (new_fm, new_body) = old, new
    if change.path.startswith("data/firmware/"):
        return _firmware_refresh_reason(old_fm, new_fm, old_body, new_body, change.path)
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
    if is_bookkeeping(path):
        return None
    if status == "D":
        return f"deletion: {path}"
    if path.startswith(SNAPSHOT_DIRS) or (_is_signals(path) and status in ("A", "M")):
        return None
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
