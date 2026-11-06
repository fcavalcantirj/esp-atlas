"""EspAtlas Jr — the demand work broker: the daily reservation step of the demand work consumer
(SPEC-demand-work-consumer.md, Required execution path step 1; Idempotence and failure recovery).

After the daily runner (jr/demand_run.py) mines, `reserve` hands the committed research queue,
the eligible GSC UNRESOLVED items of the fresh snapshot and the persisted work receipts to
research_work.plan_work, and records at most ONE new reservation in
`docs/demand/work-receipts.json`, which lands in the demand publication PR when it changed.

Bookkeeping only: no catalog write, no PR or branch for the work item, no LLM, and no network
beyond the injected `gh`, which lists the deterministic `jr/research-*` branches and their PRs in
all states, keeping each PR's state. A listing that fails, is unreadable or may be truncated is
never an empty listing: plan_work then permits nothing. An OPEN PR no live receipt accounts for is
recovered (its open candidate starts first) or defers new work; closed/merged history never blocks.
The receipts file is append-only here — an existing receipt (another candidate, its linked work,
its recorded outcome) is never rewritten — and an unreadable file or an unknown schema version is
preserved byte-for-byte and blocks new work. Writes are atomic.

Lock scope: scripts/jr-demand.sh's host-local flock serializes runs on one host, and each run
works in its own fresh worktree. That is not global exactly-once: a reservation is durable once
its demand PR merges; until then a rerun derives the same deterministic work id and branch.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

import research_queue
import research_work as rw

RECEIPTS_NAME = "work-receipts.json"
RECEIPTS_VERSION = 1
DEMAND_RELDIR = "docs/demand"
PR_LIST_LIMIT = 100          # a deterministic branch with this many PRs may be truncated: incomplete
GSC_SOURCE = "gsc_query"
GSC_METRICS = ("impressions", "clicks", "position")   # GSC units only — never GA4 counts
GAP_UNRESOLVED = "UNRESOLVED"
RESERVED = "reserved"
RESERVED_BY = "jr/demand_run.py"
PR_OPEN = "OPEN"
PR_STATES = {PR_OPEN, "CLOSED", "MERGED"}                 # gh's PR states; anything else is unreadable


# --- intake ------------------------------------------------------------------------------------

def _gsc_metrics(item: dict) -> dict:
    return {m: item[m] for m in GSC_METRICS
            if isinstance(item.get(m), (int, float)) and not isinstance(item.get(m), bool)}


def _gsc_candidate(item, snap: dict) -> dict | None:
    """A `new` candidate for an UNRESOLVED GSC demand item, in GSC's own units, or None."""
    if not isinstance(item, dict) or item.get("gap") != GAP_UNRESOLVED or item.get("resolved"):
        return None
    sources = item.get("source") if isinstance(item.get("source"), list) else [item.get("source")]
    metrics = _gsc_metrics(item)
    if GSC_SOURCE not in sources or not rw.term_key(item.get("term")) or not item.get("first_seen") or not metrics:
        return None
    return {"term": item["term"], "status": rw.STATUS_NEW, "source": GSC_SOURCE,
            "first_seen": item["first_seen"], "last_seen": item.get("last_seen"),
            "window": copy.deepcopy(snap.get("window")), "metrics": metrics,
            "linked_work": [], "history": [], "snapshot": f"{DEMAND_RELDIR}/{snap.get('date')}.json"}


def intake(queue, snap: dict) -> dict | None:
    """The broker's view: the committed queue's candidates plus each eligible GSC UNRESOLVED item
    whose term the queue does not already hold (the queue carries lifecycle state, so it wins).
    An unreadable queue is passed through for plan_work to refuse. Inputs are never mutated."""
    if not isinstance(queue, dict) or not isinstance(queue.get("candidates"), dict):
        return queue
    view = copy.deepcopy(queue)
    known = {rw.term_key(c.get("term")) for c in view["candidates"].values() if isinstance(c, dict)}
    for item in (snap or {}).get("items") or []:
        c = _gsc_candidate(item, snap)
        if c and rw.term_key(c["term"]) not in known:
            known.add(rw.term_key(c["term"]))
            view["candidates"][rw.term_key(c["term"])] = c
    return view


def _branch(candidate: dict) -> str | None:
    term, opening = candidate.get("term"), rw.opened_on(candidate)
    if not (isinstance(term, str) and rw.term_key(term) and isinstance(opening, str)):
        return None
    return rw.branch_for(rw.work_key(term, opening))


# --- the remote listing ------------------------------------------------------------------------

@dataclass
class Remote:
    complete: bool
    reason: str = ""
    branches: set = field(default_factory=set)
    prs: dict = field(default_factory=dict)        # branch -> [{"url", "state", "number"}, …] in all states

    def urls(self, branch: str) -> list:
        return [pr["url"] for pr in self.prs.get(branch, [])]

    def open_branches(self) -> set:
        return {b for b, prs in self.prs.items() if any(pr["state"] == PR_OPEN for pr in prs)}


def _json_pages(text: str) -> list | None:
    """`gh api --paginate` output: one or more JSON arrays back to back, or None. Empty output is
    unreadable, never an empty listing (an empty listing is `[]`)."""
    decoder, pages, i = json.JSONDecoder(), [], 0
    text = text.strip()
    while i < len(text):
        try:
            page, i = decoder.raw_decode(text, i)
        except ValueError:
            return None
        if not isinstance(page, list):
            return None
        pages.append(page)
        while i < len(text) and text[i].isspace():
            i += 1
    return [entry for page in pages for entry in page] if pages else None


def _remote_branches(gh, repo_slug: str | None) -> set | None:
    slug = repo_slug or "{owner}/{repo}"
    p = gh("api", f"repos/{slug}/git/matching-refs/heads/{rw.BRANCH_PREFIX}", "--paginate")
    refs = _json_pages(getattr(p, "stdout", "") or "") if getattr(p, "returncode", 1) == 0 else None
    prefix = f"refs/heads/{rw.BRANCH_PREFIX}"
    if refs is None or not all(isinstance(r, dict) and str(r.get("ref", "")).startswith(prefix) for r in refs):
        return None
    return {r["ref"].removeprefix("refs/heads/") for r in refs}


def _branch_prs(gh, branch: str) -> list | None:
    p = gh("pr", "list", "--head", branch, "--state", "all", "--limit", str(PR_LIST_LIMIT),
           "--json", "number,url,state,headRefName")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        prs = json.loads(getattr(p, "stdout", "") or "")
    except ValueError:
        return None
    if not isinstance(prs, list) or len(prs) >= PR_LIST_LIMIT:
        return None
    if not all(isinstance(pr, dict) and pr.get("headRefName") == branch and isinstance(pr.get("url"), str)
               and pr["url"].strip() and isinstance(pr.get("state"), str) and pr["state"] in PR_STATES
               for pr in prs):
        return None
    return [{"url": pr["url"], "state": pr["state"], "number": pr.get("number")} for pr in prs]


def remote_listing(gh, branches, repo_slug: str | None = None) -> Remote:
    """Every deterministic branch on the remote plus the PRs, in all states, of those branches and
    of every branch this run could act on. Complete only when every call was readable."""
    remote = _remote_branches(gh, repo_slug)
    if remote is None:
        return Remote(False, "deterministic branch listing failed or unreadable")
    prs = {}
    for branch in sorted(set(branches) | remote):
        listed = _branch_prs(gh, branch)
        if listed is None:
            return Remote(False, f"PR listing for {branch} failed, unreadable or truncated")
        prs[branch] = listed
    return Remote(True, branches=remote, prs=prs)


# --- the receipts file -------------------------------------------------------------------------

def _load_receipts(raw: bytes | None) -> dict | None:
    if raw is None:
        return {"version": RECEIPTS_VERSION, "receipts": []}
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("receipts"), list):
        return None
    version = doc.get("version")
    return doc if type(version) is int and version == RECEIPTS_VERSION else None   # unknown schema: refuse


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _load_queue(demand_dir: Path):
    raw = _read(demand_dir / research_queue.QUEUE_NAME)
    if raw is None:
        return research_queue.empty_queue()
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None


# --- reserve -----------------------------------------------------------------------------------

@dataclass
class Outcome:
    action: str
    reason: str = ""
    key: str = ""
    phase: str = ""
    changed: bool = False

    def line(self) -> str:
        if self.changed:
            return f"reserved {self.key} ({self.phase})"
        return " ".join(filter(None, [self.action, self.key])) + f": {self.reason}"


def _receipt(work: rw.Work, candidate: dict, remote: Remote, today: str) -> dict:
    prs = remote.urls(work.branch)
    receipt = {"key": work.key, "branch": work.branch, "term": work.term, "phase": work.phase,
               "state": RESERVED, "started_on": today, "source": work.source,
               "window": copy.deepcopy(work.window), "metrics": copy.deepcopy(work.metrics),
               "linked_work": list(dict.fromkeys([*work.linked_work, *prs]))}
    if prs:
        receipt["pr_url"] = prs[0]          # created before a local save: recover it, never recreate
    receipt["provenance"] = {
        "snapshot": candidate.get("snapshot") or f"{DEMAND_RELDIR}/{research_queue.QUEUE_NAME}",
        "opened_on": rw.opened_on(candidate), "status": candidate.get("status"),
        **({"classification": candidate["classification"]} if "classification" in candidate else {}),
        "remote": {"branch": work.branch in remote.branches, "prs": prs},
        "reserved_by": RESERVED_BY}
    return receipt


def _candidate_for(view: dict, key: str) -> dict:
    return next(c for c in view["candidates"].values()
                if isinstance(c, dict) and _branch(c) == rw.branch_for(key))


def reserve(demand_dir: Path, snap: dict, *, gh, today: str, repo_slug: str | None = None) -> Outcome:
    """Plan one action over the committed queue + snapshot + receipts; on START append ONE
    reservation atomically. Every other action leaves the receipts file untouched."""
    path = Path(demand_dir) / RECEIPTS_NAME
    raw = _read(path)
    doc = _load_receipts(raw)
    if doc is None:
        return Outcome(rw.DEFER, f"unreadable {RECEIPTS_NAME} or not schema version {RECEIPTS_VERSION}: "
                                 "preserved, no new reservation")
    receipts = doc["receipts"]
    view = intake(_load_queue(Path(demand_dir)), snap)
    live = [r["branch"] for r in receipts if isinstance(r, dict) and isinstance(r.get("branch"), str)
            and r.get("state") not in rw.TERMINAL_STATES]
    candidates = view.get("candidates", {}).values() if isinstance(view, dict) else []
    open_work = {b for c in candidates if isinstance(c, dict) and c.get("status") != rw.STATUS_CLOSED
                 for b in [_branch(c)] if b}
    remote = remote_listing(gh, open_work | set(live), repo_slug)
    unrecorded = remote.open_branches() - set(live)     # open remote PRs no live receipt accounts for
    plan = rw.plan_work(view, receipts, today, remote_complete=remote.complete, prefer=unrecorded)
    reason = "; ".join(filter(None, [plan.reason, remote.reason]))
    key = plan.work.key if plan.work else ""
    if plan.action != rw.START:
        return Outcome(plan.action, reason, key)
    stray = sorted(unrecorded - open_work)
    if stray:
        return Outcome(rw.DEFER, f"open remote work on {', '.join(stray)} matches no live receipt or open "
                                 "candidate: recover or close it before new work", key)
    if unrecorded and plan.work.branch not in unrecorded:
        return Outcome(rw.DEFER, f"open remote work on {', '.join(sorted(unrecorded))} cannot be recovered "
                                 "this run: no new work before it", key)
    if len(remote.prs.get(plan.work.branch, [])) > 1:
        return Outcome(rw.DEFER, f"duplicate remote PRs on {plan.work.branch}", key)
    receipt = _receipt(plan.work, _candidate_for(view, key), remote, today)
    if _read(path) != raw:
        return Outcome(rw.DEFER, f"{RECEIPTS_NAME} changed during the run: not overwritten", key)
    try:     # the queue's atomic JSON writer: temp file, fsync, os.replace — the old file survives
        research_queue.write_queue({**doc, "receipts": [*receipts, receipt]}, path)
    except OSError as e:
        return Outcome(rw.DEFER, f"{RECEIPTS_NAME} write failed, previous file kept: {e}", key)
    return Outcome(rw.START, plan.reason, key, plan.work.phase, changed=True)
