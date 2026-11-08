"""EspAtlas Jr — the demand work consumer's policy (SPEC-demand-work-consumer.md).

The research queue (jr/research_queue.py) records WHY a search found nothing; this module decides
what the consumer may DO about it on one run, and when a linked change actually delivered.

- `plan_work` picks at most one action per run: reconcile/resume existing work first (allowed at
  the cap), else start one new item when the daily cap and the remote listing allow it. A `new`
  candidate permits research only; authoring needs a readable primary-source validation receipt.
- A queue candidate a closure closed while that work's receipt is still live (`inconsistent_closures`)
  blocks every new start until a human settles the receipt.
- `verify_resolution` closes a candidate only on a merged, associated PR plus a same-day receipt
  of the postcondition its validation names: exactly the expected public search id set, with no
  forbidden or undeclared id (a possible sibling SKU), at a deployment containing the merge; or a
  fresh successful miner run at a revision containing it. Closure evidence carries the reservation's
  original provenance, not the queue's refreshed sliding window.

Pure functions over plain dicts, stdlib only: no network, no file writes, inputs never mutated.
The work key is an opaque hash of the normalized term plus its lifecycle opening date, so raw
search text never reaches a branch name, a command or a path.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field

import pam_leads

MAX_NEW_PER_DAY = 1           # newly started work items per UTC day (an item retried later keeps its slot)
KEY_HEX_CHARS = 16
BRANCH_PREFIX = "jr/research-"

STATUS_NEW, STATUS_VALIDATED, STATUS_LINKED, STATUS_CLOSED = "new", "validated", "linked", "closed"
STATUSES = {STATUS_NEW, STATUS_VALIDATED, STATUS_LINKED, STATUS_CLOSED}

NOOP, START, RESUME, RECONCILE, DEFER = "noop", "start", "resume", "reconcile", "defer"
PHASE_RESEARCH, PHASE_AUTHOR = "research", "author"

RECEIPT_STATES = {"reserved", "proposed", "deferred", "delivered", "rejected", "abandoned"}
TERMINAL_STATES = {"delivered", "rejected", "abandoned"}

KIND_CATALOG_SEARCH = "catalog_search"     # missing catalog content: exact public search ids
KIND_DEMAND_RESOLUTION = "demand_resolution"  # miner-resolver repair: a fresh resolved miner run
KIND_CATALOG_PART = "catalog_part"         # missing board: the exact public part endpoint serves each id
COVERED_GAP = "COVERED_OK"
SOURCE_PAM = "pam_feed"

# One daily work slot PER SOURCE CLASS (decision 2026-11-08): search demand (GSC/GA4) and PAM market
# leads each start at most MAX_NEW_PER_DAY new items a day and each recover their own live item, so a
# day with new search demand still starts one feed lead. plan_work(source_class=...) narrows a pass to
# one class; without it the single shared budget of before applies (direct callers, older tests).
CLASS_SEARCH, CLASS_PAM = "search", "pam"
CLASSES = {CLASS_SEARCH, CLASS_PAM}


def class_of(source) -> str:
    """The daily-slot class a work source belongs to: `pam_feed` is PAM, everything else is search."""
    return CLASS_PAM if source == SOURCE_PAM else CLASS_SEARCH


source_class = class_of


def default_verification_kind(candidate: dict) -> str:
    """The kind jr/work_record.py writes into a validation that names none: a PAM lead is a missing
    BOARD, checked at the exact part endpoint (a name hint is never an exact search); search demand
    keeps the exact public search of its term. The judge itself (verify_resolution) still reads a
    validation without a kind as catalog_search, as every validation written before 2026-11-08 was."""
    return KIND_CATALOG_PART if isinstance(candidate, dict) and candidate.get("source") == SOURCE_PAM \
        else KIND_CATALOG_SEARCH

_TOKEN_RE = re.compile(r"[^\W_]+")


# ═══════════════════════════ identity ═══════════════════════════

def term_key(term: str | None) -> str:
    """The research queue's dedupe key (research_queue.term_key, kept stdlib-only here)."""
    if not isinstance(term, str):
        return ""
    return " ".join(_TOKEN_RE.findall((term or "").casefold()))


def opened_on(candidate: dict) -> str | None:
    """The current lifecycle's opening date: the last reopening, else first_seen."""
    history = candidate.get("history") or []
    if not isinstance(history, list):
        return None
    reopens = [h.get("date") for h in history if isinstance(h, dict) and h.get("event") == "reopened"]
    return reopens[-1] if reopens else candidate.get("first_seen")


def work_key(term: str, opening_date: str) -> str:
    digest = hashlib.sha256(f"{term_key(term)}\n{opening_date}".encode()).hexdigest()
    return digest[:KEY_HEX_CHARS]


def branch_for(key: str) -> str:
    return BRANCH_PREFIX + key


def candidate_key(candidate: dict) -> str | None:
    if candidate.get("source") == SOURCE_PAM:
        feed = candidate.get("feed")
        return pam_leads.work_key(feed["lead"]) if pam_leads.readable_work_provenance(feed) else None
    term, opening = candidate.get("term"), opened_on(candidate)
    return work_key(term, opening) if term_key(term) and _date(opening) else None


# ═══════════════════════════ readable inputs ═══════════════════════════

def _date(value) -> dt.date | None:
    """Only canonical YYYY-MM-DD: dates are compared and hashed as strings, so '20261105' (which
    fromisoformat also accepts) must not pass as a second spelling of '2026-11-05'."""
    try:
        parsed = dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == value else None


def _utc(value) -> dt.datetime | None:
    try:
        stamp = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp.astimezone(dt.timezone.utc) if stamp.tzinfo else None


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _links(row: dict) -> list | None:
    """linked_work refs, or None when the field is not a list (never a substring match)."""
    links = row.get("linked_work") or []
    return links if isinstance(links, list) else None


def _window(row: dict) -> dict | None:
    w = row.get("window")
    if not isinstance(w, dict):
        return None
    start, end = _date(w.get("start")), _date(w.get("end"))
    if start is None or end is None or start > end:
        return None
    return {"start": w["start"], "end": w["end"]}


def _metrics(row: dict) -> dict | None:
    """The source's own units: GSC impressions/clicks/position stay GSC metrics, GA4 counts stay
    GA4 counts. Nothing is converted or invented."""
    metrics = row.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return copy.deepcopy(metrics)
    ga4 = {k: row[k] for k in ("searches", "zero_result_searches") if k in row}
    return ga4 or None


def _forbidden_ids(v: dict) -> list | None:
    """The sibling ids the validation ruled out ([] when it names none), or None when the list is
    unreadable or contradicts the expected set."""
    forbidden = v.get("forbidden_ids", [])
    if not (isinstance(forbidden, list) and all(_text(i) for i in forbidden)):
        return None
    return None if set(forbidden) & set(v["expected_ids"]) else forbidden


def readable_validation(candidate: dict) -> dict | None:
    """The identity/primary-source receipt, only when it names THIS term and is complete."""
    v = candidate.get("validation")
    if not isinstance(v, dict) or v.get("identity_verified") is not True:
        return None
    key = term_key(candidate.get("term"))
    if not key or term_key(v.get("term_key")) != key:
        return None
    sources, ids = v.get("primary_sources"), v.get("expected_ids")
    if not (_text(v.get("validated_by")) and _date(v.get("verified_on"))
            and isinstance(sources, list) and sources and all(_text(s) for s in sources)
            and isinstance(ids, list) and ids and all(_text(i) for i in ids)):
        return None
    return v if _forbidden_ids(v) is not None else None


_SNAPSHOT_CHECKS = {"source": lambda r: _text(r["source"]), "window": _window, "metrics": _metrics}


def _readable_receipt(r) -> bool:
    if not isinstance(r, dict) or not _text(r.get("key")):
        return False
    if not isinstance(r.get("state"), str) or r["state"] not in RECEIPT_STATES:
        return False
    if r.get("source") == SOURCE_PAM:
        if ("window" in r or "metrics" in r or not pam_leads.readable_work_provenance(r.get("feed"))
                or r["key"] != pam_leads.work_key(r["feed"]["lead"])
                or term_key(r.get("term")) != term_key(r["feed"]["lead"]["name_hint"])):
            return False
    elif any(f in r and not check(r) for f, check in _SNAPSHOT_CHECKS.items()):
        return False
    if r.get("branch") != branch_for(r["key"]) or _date(r.get("started_on")) is None:
        return False
    if "last_attempt_on" in r and _date(r["last_attempt_on"]) is None:
        return False
    return "pr_url" not in r or _text(r["pr_url"])


# ═══════════════════════════ plan_work ═══════════════════════════

@dataclass(frozen=True)
class Work:
    key: str
    branch: str
    term: str
    phase: str
    source: str
    window: dict | None
    metrics: dict | None
    linked_work: tuple = ()
    feed: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    action: str
    work: Work | None = None
    reason: str = ""


def _provenance(candidate: dict, own: list[dict]) -> dict:
    """The signal this work answers: the earliest receipt's snapshot when one was persisted (the
    queue refreshes window/counts daily, so the reservation's copy is the original), else the
    candidate's current fields."""
    snapshots = sorted((r for r in own if (r.get("source") == SOURCE_PAM
                        or all(f in r for f in _SNAPSHOT_CHECKS))), key=lambda r: r["started_on"])
    row = snapshots[0] if snapshots else candidate
    if row.get("source") == SOURCE_PAM:
        return {"source": SOURCE_PAM, "window": None, "metrics": None,
                "feed": copy.deepcopy(row.get("feed"))}
    return {"source": row.get("source"), "window": _window(row), "metrics": _metrics(row)}


def _work(candidate: dict, receipts: list[dict]) -> Work | None:
    """The work item for a candidate's current lifecycle, or None when its provenance is not
    readable (no source, window, metrics, opening date or linked_work list): it fails closed."""
    term, opening, links = candidate.get("term"), opened_on(candidate), _links(candidate)
    if not (term_key(term) and _date(opening) and links is not None):
        return None
    key = candidate_key(candidate)
    if key is None:
        return None
    own = [r for r in receipts if r["key"] == key]
    prov = _provenance(candidate, own)
    if prov["source"] == SOURCE_PAM:
        if ("window" in candidate or "metrics" in candidate
                or not pam_leads.readable_work_provenance(prov["feed"])
                or key != pam_leads.work_key(prov["feed"]["lead"])
                or term_key(term) != term_key(prov["feed"]["lead"]["name_hint"])):
            return None
    elif not (_text(prov["source"]) and prov["window"] and prov["metrics"]):
        return None
    refs = [ref for ref in links if _text(ref)] + [r["pr_url"] for r in own if "pr_url" in r]
    phase = PHASE_AUTHOR if (candidate.get("status") in (STATUS_VALIDATED, STATUS_LINKED)
                             and readable_validation(candidate)) else PHASE_RESEARCH
    return Work(key=key, branch=branch_for(key), term=term, phase=phase, linked_work=tuple(dict.fromkeys(refs)),
                **prov)


def _existing_action(candidate: dict, own: list[dict], today: str) -> str | None:
    """reconcile / resume for a candidate that already has work this lifecycle, else None."""
    if candidate.get("status") == STATUS_LINKED or _links(candidate):
        return RECONCILE                            # existing controller work is reconciled, never duplicated
    live = [r for r in own if r["state"] not in TERMINAL_STATES]
    if not live:
        return None
    if any("pr_url" in r for r in own):
        return RECONCILE
    last = max(r.get("last_attempt_on") or r["started_on"] for r in live)
    return RECONCILE if last >= today else RESUME   # one attempt per day; a later day retries


def _open_candidates(queue) -> list[dict] | None:
    rows = queue.get("candidates") if isinstance(queue, dict) else None
    if not isinstance(rows, dict) or not all(isinstance(c, dict) for c in rows.values()):
        return None
    return sorted(rows.values(), key=lambda c: (term_key(c.get("term")), str(c.get("term"))))


def _closure_work(candidate: dict) -> str | None:
    """The work id a broker closure recorded on a closed candidate (its last history entry), else None.
    A candidate closed by hand records no such entry."""
    history = candidate.get("history")
    last = history[-1] if isinstance(history, list) and history else None
    if candidate.get("status") != STATUS_CLOSED or not isinstance(last, dict) or last.get("event") != "closed":
        return None
    return last["work"] if _text(last.get("work")) else None


def inconsistent_closures(queue, receipts) -> list[str]:
    """Work ids a closure closed in the queue while a receipt for that work is still live: the
    receipts write and the queue restore both failed, or a foreign queue write won the race.
    Sorted; [] when the queue is unreadable (plan_work refuses that on its own)."""
    rows = _open_candidates(queue)
    if rows is None:
        return []
    closed = {_closure_work(c) for c in rows} - {None}
    live = {r.get("key") for r in receipts or [] if isinstance(r, dict) and r.get("state") not in TERMINAL_STATES}
    return sorted(closed & live)


def one_sided_closures(queue, receipts, base_receipts=()) -> list[str]:
    """Work ids whose closure the pair records on one side only, in either direction: a receipt a
    closure settled (it carries the closure's `resolution`) with no closed event for that work in the
    queue's history, or a closed candidate whose receipt — in `receipts` or the `base_receipts` it
    was settled from — is absent or still live. A closure that had no receipt to settle needs none.
    Sorted; [] when the queue is unreadable (plan_work refuses that on its own)."""
    rows = _open_candidates(queue)
    if rows is None:
        return []
    rows_of = [r for r in receipts or [] if isinstance(r, dict)]
    recorded = {h.get("work") for c in rows for h in c.get("history") or []
                if isinstance(h, dict) and h.get("event") == "closed"}
    settled = {r.get("key") for r in rows_of
               if r.get("state") in TERMINAL_STATES and isinstance(r.get("resolution"), dict)}
    present = {r.get("key") for r in rows_of}
    live = {r.get("key") for r in rows_of if r.get("state") not in TERMINAL_STATES}
    had = {r.get("key") for r in base_receipts or [] if isinstance(r, dict)}
    closed = {_closure_work(c) for c in rows} - {None}
    return sorted((settled - recorded) | (closed & (live | (had - present))))


def plan_work(queue: dict, receipts: list[dict], today: str, *, remote_complete: bool = False,
              prefer: set | frozenset = frozenset(), source_class: str | None = None) -> Plan:
    """The one action this run may take. `receipts` are the consumer's persisted work receipts;
    `remote_complete` says the deterministic branches and PRs/issues in all states were listed
    completely. An uncertain listing permits nothing: no blind create, no resumed execution.
    `prefer` names branches whose remote work exists unrecorded: such work starts first, so it is
    recovered before any other new work takes the day's slot. `source_class` (CLASS_SEARCH or
    CLASS_PAM) narrows the pass to one daily-slot class: only that class's live work is recovered or
    reconciled, only its candidates may start, and the daily cap counts that class's starts; the
    fail-closed checks over the whole pair (unreadable receipts, unknown statuses, orphans,
    inconsistent closures) still block every class. None keeps the single shared budget."""
    if source_class is not None and source_class not in CLASSES:
        raise ValueError(f"unknown work source class {source_class!r}: one of {sorted(CLASSES)}")
    if _date(today) is None:
        return Plan(DEFER, reason=f"unreadable run date {today!r}")
    if not remote_complete:
        return Plan(DEFER, reason="remote work listing incomplete or unreadable: no create or resume")
    receipts = list(receipts or [])
    if not all(_readable_receipt(r) for r in receipts):
        return Plan(DEFER, reason="corrupt work receipt: fail closed")
    rows = _open_candidates(queue)
    if rows is None:
        return Plan(DEFER, reason="unreadable research queue")

    blocked = [f"inconsistent closure of work {k}: the queue closed it but its receipt is still live; "
               "settle that receipt before new work"
               for k in inconsistent_closures(queue, receipts)]
    startable, settled_keys, open_keys = [], set(), set()
    for c in rows:
        if not isinstance(c.get("status"), str) or c["status"] not in STATUSES:
            blocked.append(f"{c.get('term')!r}: unknown status {c.get('status')!r}")
            continue
        work = _work(c, receipts)
        if c["status"] == STATUS_CLOSED:
            if work:
                settled_keys.add(work.key)
            continue
        if work is None:
            blocked.append(f"{c.get('term')!r}: missing provenance (source/window/metrics/date)")
            continue
        open_keys.add(work.key)
        own = [r for r in receipts if r["key"] == work.key]
        if len({r["pr_url"] for r in own if "pr_url" in r}) > 1:
            blocked.append(f"{work.term!r}: duplicate remote PRs for work {work.key}")
            continue
        in_class = source_class is None or class_of(work.source) == source_class
        action = _existing_action(c, own, today)
        if action and in_class:
            return Plan(action, work, reason=f"existing work {work.key}")
        if not action and not own and in_class:
            startable.append((c, work))        # another class's live work is that class's pass to recover

    orphans = {r["key"] for r in receipts if r["state"] not in TERMINAL_STATES} - open_keys - settled_keys
    if blocked or orphans:
        detail = blocked + [f"outstanding work {k} matches no open candidate" for k in sorted(orphans)]
        return Plan(DEFER, reason="; ".join(detail))
    if not startable:
        return Plan(NOOP, reason="no open candidate needs work")
    started = {r["key"] for r in receipts if r["started_on"] == today
               and (source_class is None or class_of(r.get("source")) == source_class)}
    if len(started) >= MAX_NEW_PER_DAY:
        which = f" {source_class}" if source_class else ""
        return Plan(DEFER, reason=f"daily cap of {MAX_NEW_PER_DAY} new{which} work item(s) reached")
    startable.sort(key=lambda cw: (cw[1].branch not in prefer, cw[1].source == SOURCE_PAM,
                                  cw[1].phase != PHASE_AUTHOR))  # search demand before market leads
    return Plan(START, startable[0][1], reason="new work")


# ═══════════════════════════ verify_resolution ═══════════════════════════

@dataclass(frozen=True)
class Resolution:
    status: str                       # delivered | rejected | pending
    reason: str
    closed_on: str | None = None
    evidence: dict = field(default_factory=dict)


def _pending(reason: str) -> Resolution:
    return Resolution("pending", reason)


def _merge_problem(candidate: dict, pr: dict) -> Resolution | None:
    if not isinstance(pr, dict) or not _text(pr.get("url")) or pr["url"] not in (_links(candidate) or []):
        return _pending("PR is not linked to this candidate")
    if pr.get("merged") is True:
        if _text(pr.get("merge_sha")) and _utc(pr.get("merged_at")):
            return None
        return _pending("merged PR has no readable merge SHA/time")
    if pr.get("state") == "closed" and pr.get("merged") is False:
        return Resolution("rejected", pr.get("rejection_reason") or "PR closed without merging")
    return _pending("PR not merged")


def _receipt_problem(receipt: dict, candidate: dict, pr: dict, kind: str, today: str) -> str | None:
    """Shared freshness/association rules: same kind, same query, the same merge, observed
    after the merge on today's UTC day."""
    if receipt.get("kind", KIND_CATALOG_SEARCH) != kind:
        return f"receipt is not a {kind} verification"
    if not _text(receipt.get("query")) or term_key(receipt["query"]) != term_key(candidate.get("term")):
        return "receipt checks a different query"
    if receipt.get("merge_sha") != pr["merge_sha"] or receipt.get("contains_merge") is not True:
        return "receipt does not observe a revision containing this merge"
    checked = _utc(receipt.get("checked_at"))
    if checked is None or checked < _utc(pr["merged_at"]):
        return "receipt predates the merge or has no readable time"
    if checked.date().isoformat() != today:
        return "receipt was not observed today"
    return None


def _catalog_search_problem(receipt: dict, expected: list, forbidden: list) -> str | None:
    """Exact-SKU: the response is exactly the declared expected set, order irrelevant. A missing
    id (a partial positive) stays open; so does any extra id, forbidden or merely undeclared — it
    may be a sibling the validation never named. Unreadable ids stay open, never raise."""
    if receipt.get("http") != 200 or not _text(receipt.get("deployment")):
        return "live search not successful at a known deployment"
    ids = receipt.get("ids")
    if not (isinstance(ids, list) and all(_text(i) for i in ids)):
        return "live search ids unreadable"
    missing = [i for i in expected if i not in ids]
    if missing:
        return f"live search lacks expected ids {missing}"
    siblings = [i for i in forbidden if i in ids]
    if siblings:
        return f"live search also returns forbidden sibling ids {siblings}"
    extra = sorted(set(ids) - set(expected))
    return f"live search also returns undeclared ids {extra}" if extra else None


def _demand_resolution_problem(receipt: dict, expected: list, forbidden: list) -> str | None:
    if receipt.get("exit_code") != 0 or not _text(receipt.get("mined_revision")):
        return "no successful miner run at a known revision"
    resolved = receipt.get("resolved") if isinstance(receipt.get("resolved"), dict) else {}
    if resolved.get("board") not in expected:   # expected and forbidden are disjoint
        return f"miner resolved {resolved.get('board')!r}, not {expected}"
    if receipt.get("gap") != COVERED_GAP:
        return f"miner gap is {receipt.get('gap')!r}, not {COVERED_GAP}"
    return None


def _catalog_part_problem(receipt: dict, expected: list, forbidden: list) -> str | None:
    """Exact parts: every expected id is served by the public part endpoint (and listed by a search
    for that very id) at the deployment, and no forbidden sibling is. A missing id stays open; a
    forbidden one present stays open. Unreadable lists stay open, never raise."""
    if receipt.get("http") != 200 or not _text(receipt.get("deployment")):
        return "live part reads not successful at a known deployment"
    lists = {f: receipt.get(f) for f in ("ids", "missing", "forbidden_hits")}
    for name, value in lists.items():
        if not (isinstance(value, list) and all(_text(i) for i in value)):
            return f"live part {name} unreadable"
    absent = [i for i in expected if i not in lists["ids"] or i in lists["missing"]]
    if absent:
        return f"live catalog lacks expected parts {absent}"
    siblings = [i for i in forbidden if i in lists["forbidden_hits"] or i in lists["ids"]]
    if siblings:
        return f"live catalog also serves forbidden sibling parts {siblings}"
    return None


_KIND_CHECKS = {KIND_CATALOG_SEARCH: (_catalog_search_problem, ("http", "deployment", "ids")),
                KIND_DEMAND_RESOLUTION: (_demand_resolution_problem,
                                         ("mined_revision", "exit_code", "resolved", "gap")),
                KIND_CATALOG_PART: (_catalog_part_problem,
                                    ("http", "deployment", "ids", "missing", "forbidden_hits"))}


def verify_resolution(candidate: dict, pr: dict, observed_receipt: dict, today: str, *,
                      work_receipts: list[dict] | None = None) -> Resolution:
    """delivered (closed_on=today, with evidence) only for the linked, merged PR plus a same-day
    receipt of the postcondition the validation's verification kind names; rejected for a PR
    closed unmerged; pending for everything else, including any unreadable input. The evidence's
    source/window/metrics come from this work's reservation in `work_receipts` (the consumer's
    persisted receipts) when one was snapshotted, else from the candidate."""
    if not isinstance(candidate, dict) or candidate.get("status") != STATUS_LINKED or _date(today) is None:
        return _pending("candidate is not linked work or the run date is unreadable")
    validation = readable_validation(candidate)
    if validation is None:
        return _pending("no readable identity validation")
    merge = _merge_problem(candidate, pr)
    if merge:
        return merge
    kind = validation.get("verification_kind", KIND_CATALOG_SEARCH)
    if not isinstance(kind, str) or kind not in _KIND_CHECKS:
        return _pending(f"unknown verification kind {kind!r}")
    if not isinstance(observed_receipt, dict):
        return _pending("no readable verification receipt")
    check, fields = _KIND_CHECKS[kind]
    forbidden = _forbidden_ids(validation)
    problem = (_receipt_problem(observed_receipt, candidate, pr, kind, today)
               or check(observed_receipt, validation["expected_ids"], forbidden))
    if problem:
        return _pending(problem)
    receipts = list(work_receipts or [])
    if not all(_readable_receipt(r) for r in receipts):
        return _pending("corrupt work receipt: fail closed")
    work = _work(candidate, receipts)
    if work is None:
        return _pending("unreadable provenance (source/window/metrics/date)")
    evidence = {"pr_url": pr["url"], "merge_sha": pr["merge_sha"], "merged_at": pr["merged_at"],
                "verification_kind": kind, "query": observed_receipt["query"],
                "checked_at": observed_receipt["checked_at"],
                "expected_ids": list(validation["expected_ids"]), "forbidden_ids": list(forbidden),
                "source": work.source}
    if work.source == SOURCE_PAM:
        evidence["feed"] = copy.deepcopy(work.feed)
    else:
        evidence.update(window=dict(work.window), metrics=work.metrics)
    evidence.update({f: copy.deepcopy(observed_receipt[f]) for f in fields})
    return Resolution("delivered", f"{kind} postcondition observed", closed_on=today, evidence=evidence)
