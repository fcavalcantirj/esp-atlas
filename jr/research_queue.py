"""EspAtlas Jr — the zero-result site-search research queue (SPEC-demand-research-queue.md).

The demand steer floors every site-search term at MIN_EVENTS (jr/demand.py); a single search
that found nothing never reaches it. This module keeps that evidence as a RESEARCH candidate in
`docs/demand/research-queue.json`: deduped by normalized term, rate-limited per day, and
classified offline — missing_content / alias_typo / search_defect / unclear — with the matching
catalog ids as evidence, before anyone proposes a change.

It only proposes. It never writes under `data/` (write_queue refuses the path) and never authors
a catalog record; a candidate becomes work only when a human validates and links it (the CLI at
the bottom). Everything but the catalog/queue file reads is a pure function over plain dicts.

Run: python3 jr/research_queue.py {validate,link,close} <term> …
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

JR_DIR = Path(__file__).resolve().parent
REPO = JR_DIR.parent
QUEUE_NAME = "research-queue.json"
QUEUE_PATH = REPO / "docs" / "demand" / QUEUE_NAME
QUEUE_VERSION = 1

MAX_NEW_PER_DAY = 5
REOPEN_AFTER_DAYS = 30
MAX_EVIDENCE_IDS = 3          # a fuzzy match against more distinct ids than this is ambiguous
MIN_IDENTITY_CHARS = 3        # shorter compact terms carry no identity
MIN_FUZZY_CHARS = 4           # shorter terms are only matched exactly
LONG_TERM_CHARS = 10          # from here on, two edits are still "a typo"

STATUS_NEW, STATUS_VALIDATED, STATUS_LINKED, STATUS_CLOSED = "new", "validated", "linked", "closed"
ALIAS_TYPO, SEARCH_DEFECT, MISSING_CONTENT, UNCLEAR = "alias_typo", "search_defect", "missing_content", "unclear"

# generic words that never identify a catalog entry on their own
GENERIC_WORDS = {"esp32", "esp", "firmware", "board", "boards", "device", "module", "chip", "dev",
                 "kit", "devkit", "for", "the", "and", "on", "with", "a", "an", "of", "to", "how"}

# (dir under data/, record file, kind) — the parts behind /parts/<id> are socs + modules
CATALOG_SOURCES = (("boards/*/*", "board.md", "board"), ("firmware/*", "firmware.md", "firmware"),
                   ("socs/*", "chip.md", "part"), ("modules/*", "module.md", "part"),
                   ("brands/*", "brand.md", "brand"))

_TOKEN_RE = re.compile(r"[^\W_]+")       # Unicode letters/digits: 'módulo', '开发板' are terms too


# ═══════════════════════════ normalization ═══════════════════════════

def _tokens(text: str | None) -> list[str]:
    return _TOKEN_RE.findall((text or "").casefold())


def term_key(term: str | None) -> str:
    """The dedupe key: lowercase, every run of non-alphanumerics (space, punctuation, '-', '_')
    collapsed to one space — 'ESP32-C6' == 'esp32 c6' == ' esp32_c6! '."""
    return " ".join(_tokens(term))


def compact(text: str | None) -> str:
    """Alphanumerics only, for catalog comparison — 't-beam' == 'tbeam'."""
    return "".join(_tokens(text))


def edit_distance(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, or cap + 1 as soon as it is known to exceed `cap`."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# ═══════════════════════════ the catalog index (read-only) ═══════════════════════════

def _frontmatter(md: Path) -> dict:
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    fm = yaml.safe_load(text.split("---", 2)[1]) or {}
    return fm if isinstance(fm, dict) else {}


def load_catalog(repo: Path = REPO) -> list[dict]:
    """Every catalog entry's id, title (`name`) and aliases (`aka`) — boards, firmware, parts
    (socs + modules) and brands. Reads data/ only; writes nothing."""
    out = []
    for pattern, record, kind in CATALOG_SOURCES:
        for md in sorted((repo / "data").glob(f"{pattern}/{record}")):
            fm = _frontmatter(md)
            aliases = fm.get("aka") or []
            out.append({"id": str(fm.get("id") or md.parent.name), "kind": kind,
                        "title": str(fm.get("name") or ""),
                        "aliases": [str(a) for a in aliases] if isinstance(aliases, list) else []})
    return out


def _labels(entry: dict):
    yield "id", entry["id"]
    if entry.get("title"):
        yield "title", entry["title"]
    for alias in entry.get("aliases") or []:
        yield "alias", alias


# ═══════════════════════════ classification — pure, explicit evidence ═══════════════════════════

def _match(entry: dict, via: str, label: str, distance: int) -> dict:
    return {"id": entry["id"], "kind": entry["kind"], "via": via, "label": label, "distance": distance}


def _evidence(rule: str, matches: list[dict], checked: int) -> dict:
    ids = list(dict.fromkeys(m["id"] for m in matches))
    return {"rule": rule, "ids": ids, "matches": matches, "checked": checked}


def _exact_matches(term_c: str, catalog: list[dict]) -> list[dict]:
    return [_match(e, via, label, 0) for e in catalog for via, label in _labels(e)
            if via != "alias" and compact(label) == term_c]


def _identity(text: str) -> frozenset[str]:
    """The tokens that can identify an entry — everything but GENERIC_WORDS."""
    return frozenset(t for t in _tokens(text) if t not in GENERIC_WORDS)


def _fuzzy_matches(term: str, term_c: str, catalog: list[dict]) -> list[dict]:
    """An exact alias, the same identity tokens in any order ('marauder' ~ 'ESP32 Marauder'), or
    a small edit distance."""
    cap = 2 if len(term_c) >= LONG_TERM_CHARS else 1
    term_identity = _identity(term)
    out = []
    for entry in catalog:
        best = None
        for via, label in _labels(entry):
            label_c = compact(label)
            if len(label_c) < MIN_IDENTITY_CHARS:
                continue
            if _identity(label) == term_identity:
                d = 0
            elif len(term_c) >= MIN_FUZZY_CHARS or label_c == term_c:
                d = edit_distance(term_c, label_c, cap)
            else:
                continue
            if d <= cap and (best is None or d < best["distance"]):
                best = _match(entry, via, label, d)
        if best:
            out.append(best)
    return sorted(out, key=lambda m: (m["distance"], m["id"]))


def classify(term: str, catalog: list[dict]) -> tuple[str, dict]:
    """(classification, evidence) for a zero-result term. First rule wins: an exact id/title →
    search_defect; no identity → unclear; a fuzzy id/title/alias match → alias_typo (unclear when
    more than MAX_EVIDENCE_IDS ids match); nothing → missing_content."""
    term_c, checked = compact(term), len(catalog)
    exact = _exact_matches(term_c, catalog) if term_c else []
    if exact:
        return SEARCH_DEFECT, _evidence("exact id/title match, yet the search returned nothing", exact, checked)
    tokens = _tokens(term)
    if len(term_c) < MIN_IDENTITY_CHARS or all(t in GENERIC_WORDS for t in tokens):
        return UNCLEAR, _evidence("no identity: too short or only generic words", [], checked)
    fuzzy = _fuzzy_matches(term, term_c, catalog)
    if len({m["id"] for m in fuzzy}) > MAX_EVIDENCE_IDS:
        return UNCLEAR, _evidence(f"ambiguous: fuzzy-matches more than {MAX_EVIDENCE_IDS} ids", fuzzy, checked)
    if fuzzy:
        return ALIAS_TYPO, _evidence("fuzzy id/title/alias match (alias, identity tokens or edit distance)",
                                     fuzzy, checked)
    return MISSING_CONTENT, _evidence("no catalog id, title or alias matches", [], checked)


# ═══════════════════════════ the queue — dedupe + rate limit ═══════════════════════════

def empty_queue() -> dict:
    return {"version": QUEUE_VERSION, "max_new_per_day": MAX_NEW_PER_DAY,
            "reopen_after_days": REOPEN_AFTER_DAYS, "candidates": {}}


def _days_between(start: str | None, end: str) -> int | None:
    try:
        return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


def _opened_on(c: dict) -> str | None:
    reopens = [h["date"] for h in c.get("history") or [] if h.get("event") == "reopened"]
    return reopens[-1] if reopens else c.get("first_seen")


def _candidate_rows(rows: list[dict]) -> dict[str, dict]:
    """Zero-result rows with at least one submitted search, merged per key (case/spacing
    variants of one day's pull), in rate-limit order."""
    merged: dict[str, dict] = {}
    for r in rows or []:
        key = term_key(r.get("term"))
        if not key:
            continue
        m = merged.setdefault(key, {"term": r["term"], "searches": 0, "zero_result_searches": 0})
        m["searches"] += int(r.get("searches") or 0)
        m["zero_result_searches"] += int(r.get("zero_result_searches") or 0)
    hits = {k: v for k, v in merged.items() if v["searches"] >= 1 and v["zero_result_searches"] >= 1}
    order = sorted(hits, key=lambda k: (-hits[k]["zero_result_searches"], -hits[k]["searches"], k))
    return {k: hits[k] for k in order}


def _new_candidate(r: dict, today: str, catalog: list[dict]) -> dict:
    cls, ev = classify(r["term"], catalog)
    return {"term": r["term"], "first_seen": today, "last_seen": today,
            "searches": r["searches"], "zero_result_searches": r["zero_result_searches"],
            "status": STATUS_NEW, "classification": cls, "evidence": ev,
            "linked_work": [], "outcome": None, "closed_on": None, "history": []}


def _refresh(c: dict, r: dict, today: str, catalog: list[dict]) -> None:
    c.update(last_seen=today, searches=r["searches"], zero_result_searches=r["zero_result_searches"])
    if c["status"] == STATUS_NEW:
        c["classification"], c["evidence"] = classify(c["term"], catalog)


def _reopen(c: dict, r: dict, today: str, catalog: list[dict]) -> None:
    c.setdefault("history", []).append({"event": "reopened", "date": today, "closed_on": c.get("closed_on"),
                                        "outcome": c.get("outcome"), "linked_work": c.get("linked_work") or []})
    c.update(status=STATUS_NEW, outcome=None, closed_on=None, linked_work=[])
    _refresh(c, r, today, catalog)


def update_queue(queue: dict, rows: list[dict], catalog: list[dict], today: str,
                 max_new_per_day: int | None = None,
                 reopen_after_days: int | None = None) -> tuple[dict, dict]:
    """Fold one GA4 window's `{term, searches, zero_result_searches}` rows into the queue (in
    place, also returned) and report what happened. Append-only: nothing is deleted, and a
    human's status/linked_work/outcome is never overwritten. The cap and reopen window come from
    the arguments, else the queue file's own settings, else the defaults."""
    max_new_per_day = max_new_per_day if max_new_per_day is not None else int(
        queue.get("max_new_per_day", MAX_NEW_PER_DAY))
    reopen_after_days = reopen_after_days if reopen_after_days is not None else int(
        queue.get("reopen_after_days", REOPEN_AFTER_DAYS))
    candidates = queue.setdefault("candidates", {})
    report = {"opened": [], "reopened": [], "refreshed": [], "deferred": [], "suppressed_closed": []}
    slots = max_new_per_day - sum(1 for c in candidates.values() if _opened_on(c) == today)
    for key, r in _candidate_rows(rows).items():
        c = candidates.get(key)
        if c is not None and c["status"] != STATUS_CLOSED:
            _refresh(c, r, today, catalog)
            report["refreshed"].append(key)
            continue
        if c is not None:
            age = _days_between(c.get("closed_on") or c.get("last_seen"), today)
            if age is None or age < reopen_after_days:       # an unreadable date fails closed
                report["suppressed_closed"].append(key)
                continue
        if slots <= 0:
            report["deferred"].append(key)
            continue
        slots -= 1
        if c is None:
            candidates[key] = _new_candidate(r, today, catalog)
            report["opened"].append(key)
        else:
            _reopen(c, r, today, catalog)
            report["reopened"].append(key)
    queue["candidates"] = dict(sorted(candidates.items()))
    return queue, report


# ═══════════════════════════ lifecycle — connect candidates to work ═══════════════════════════

def _get(queue: dict, term: str) -> dict:
    key = term_key(term)
    if key not in queue.get("candidates", {}):
        raise KeyError(f"no research candidate {key!r}")
    return queue["candidates"][key]


def validate(queue: dict, term: str) -> dict:
    c = _get(queue, term)
    if c["status"] != STATUS_NEW:
        raise ValueError(f"only a 'new' candidate can be validated (this one is '{c['status']}')")
    c["status"] = STATUS_VALIDATED
    return c


def link(queue: dict, term: str, ref: str) -> dict:
    c = _get(queue, term)
    if c["status"] not in (STATUS_VALIDATED, STATUS_LINKED):
        raise ValueError(f"work links only to a validated candidate (this one is '{c['status']}')")
    if ref not in c["linked_work"]:
        c["linked_work"].append(ref)
    c["status"] = STATUS_LINKED
    return c


def close(queue: dict, term: str, outcome: str, today: str) -> dict:
    c = _get(queue, term)
    try:
        dt.date.fromisoformat(today)
    except (TypeError, ValueError):
        raise ValueError(f"close date must be YYYY-MM-DD, got {today!r}") from None
    if c["status"] == STATUS_CLOSED:
        raise ValueError("this candidate is already closed")
    c.update(status=STATUS_CLOSED, outcome=outcome, closed_on=today)
    return c


# ═══════════════════════════ file I/O + digest ═══════════════════════════

def load_queue(path: Path = QUEUE_PATH) -> dict:
    """The queue file, or an empty queue when absent. An unreadable file raises: the queue holds
    human triage, so it is never silently reset."""
    path = Path(path)
    if not path.exists():
        return empty_queue()
    try:
        queue = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name} is not valid JSON: {e}") from e
    if not isinstance(queue, dict) or not isinstance(queue.get("candidates"), dict):
        raise ValueError(f"{path.name} has no candidates map")
    return queue


def write_queue(queue: dict, path: Path = QUEUE_PATH) -> Path:
    path = Path(path)
    data_dir = (REPO / "data").resolve()
    if path.resolve().is_relative_to(data_dir):
        raise ValueError("the research queue never writes under data/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queue, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def digest_line(queue: dict, report: dict) -> str:
    """One line for the demand digest / PR body: what this run did and what is open."""
    open_c = [c for c in queue.get("candidates", {}).values() if c.get("status") != STATUS_CLOSED]
    by_cls: dict[str, int] = {}
    for c in open_c:
        by_cls[c.get("classification")] = by_cls.get(c.get("classification"), 0) + 1
    mix = " · ".join(f"{k} {v}" for k, v in sorted(by_cls.items())) or "none"
    bits = [f"+{len(report.get('opened', []))} new"]
    if report.get("reopened"):
        bits.append(f"{len(report['reopened'])} reopened")
    if report.get("deferred"):
        bits.append(f"{len(report['deferred'])} deferred (cap {queue.get('max_new_per_day', MAX_NEW_PER_DAY)}/day)")
    return f"🔬 research queue: {' · '.join(bits)} — {len(open_c)} open ({mix})"


# ═══════════════════════════ CLI ═══════════════════════════

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EspAtlas Jr research queue — triage zero-result searches")
    ap.add_argument("--queue", default=str(QUEUE_PATH), help="queue file (default docs/demand/research-queue.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").add_argument("term")
    p_link = sub.add_parser("link")
    p_link.add_argument("term")
    p_link.add_argument("ref", help="PR / issue / branch the candidate is worked in")
    p_close = sub.add_parser("close")
    p_close.add_argument("term")
    p_close.add_argument("outcome")
    p_close.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    queue = load_queue(Path(args.queue))
    try:
        if args.cmd == "validate":
            c = validate(queue, args.term)
        elif args.cmd == "link":
            c = link(queue, args.term, args.ref)
        else:
            c = close(queue, args.term, args.outcome, args.date)
    except (KeyError, ValueError) as e:
        print(f"research-queue: {e}", file=sys.stderr)
        return 1
    write_queue(queue, Path(args.queue))
    print(f"research-queue: {term_key(args.term)} → {c['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
