"""EspAtlas Jr — the demand work broker: the daily reservation step of the demand work consumer
(SPEC-demand-work-consumer.md, Required execution path step 1; Idempotence and failure recovery).

After the daily runner (jr/demand_run.py) mines, `reserve` hands the committed research queue,
the eligible GSC UNRESOLVED items of the fresh snapshot, typed PAM potential identity gaps
and the persisted work receipts to
research_work.plan_work, and records at most ONE new reservation in
`docs/demand/work-receipts.json`, which lands in the demand publication PR when it changed.
When the plan is RECONCILE, jr/demand_closure.py verifies the linked work against this run's mined
snapshot; a delivered or rejected verdict closes the candidate in `research-queue.json` and settles
its receipt, then the broker re-plans once so the next eligible candidate can start the same run.

Bookkeeping only: no catalog write, no PR or branch for the work item, no LLM, and no network
beyond the injected `gh` and `git`: gh lists the deterministic `jr/research-*` branches and their
PRs in all states, keeping each PR's state, and reads a linked PR's merge; git only answers whether
that merge is an ancestor of the mined revision. A listing that fails, is unreadable or may be truncated is
never an empty listing: plan_work then permits nothing. An OPEN PR no live receipt accounts for is
recovered (its open candidate starts first) or defers new work; closed/merged history never blocks.
Rows are never deleted. A reservation only appends; a closure only settles its OWN live receipt
(state + resolution; provenance, attempt and linked work kept) and its own candidate (history
appended) — another candidate, another receipt or a recorded outcome is never rewritten. An
unreadable file or an unknown schema version is preserved byte-for-byte and blocks new work.
Writes are atomic and compare-and-swap: a file that changed since this call read it is never
overwritten (a closure checks both files, closes the queue first, and restores the read bytes
when the receipts write fails — only over its own write, never over a later writer's).

Lock scope: scripts/jr-demand.sh's host-local flock serializes runs on one host, and each run
works in its own fresh worktree. That is not global exactly-once: a reservation is durable once
its demand PR merges; until then a rerun derives the same deterministic work id and branch.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import demand_closure
import research_queue
import research_work as rw
import pam_leads
import pam_run

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


def intake(queue, snap: dict, *, pam_state=None, receipts=(), new_pam=True,
           recovering_pam_keys=()) -> dict | None:
    """The broker's view: the committed queue's candidates plus each eligible GSC UNRESOLVED item
    whose term the queue does not already hold (the queue carries lifecycle state, so it wins).
    Typed feed gaps join behind search demand; original PAM lifecycle snapshots recover first.
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
    # Preserve reserved market work even when the latest feed no longer lists it
    # or now matches the catalog. A fresh discovery list never erases its lifecycle.
    for receipt in receipts:
        if isinstance(receipt, dict) and receipt.get("source") == rw.SOURCE_PAM:
            c = receipt.get("candidate")
            if isinstance(c, dict) and rw.candidate_key(c) == receipt.get("key"):
                view["candidates"].setdefault(receipt["key"], copy.deepcopy(c))
    if pam_state is not None:
        handled = {r.get("key") for r in receipts if isinstance(r, dict)}
        recovering = set(recovering_pam_keys)
        for lead in pam_leads.candidate_leads(pam_state, handled_keys=handled, recovering_keys=recovering):
            if not new_pam and lead["key"] not in recovering:
                continue
            # An exact search identity owns its work; the feed must not create a
            # parallel market job for it. Primary-source validation still follows.
            if rw.term_key(lead["name_hint"]) in known and lead["key"] not in recovering:
                continue
            original = next(x for x in pam_state["leads"] if x["source_id"] == lead["source_id"])
            c = {"term": lead["name_hint"], "source": rw.SOURCE_PAM, "status": rw.STATUS_NEW,
                 "first_seen": lead["provenance"]["checked_at"][:10], "history": [], "linked_work": [],
                 "snapshot": pam_run.STATE_PATH,
                 "feed": {**copy.deepcopy(lead["provenance"]), "lead": copy.deepcopy(original)}}
            view["candidates"].setdefault(lead["key"], c)
    return view


def _branch(candidate: dict) -> str | None:
    key = rw.candidate_key(candidate)
    return rw.branch_for(key) if key else None


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
    """(raw bytes, parsed queue): an absent file is an empty queue, an unreadable one None."""
    raw = _read(demand_dir / research_queue.QUEUE_NAME)
    if raw is None:
        return raw, research_queue.empty_queue()
    try:
        return raw, json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw, None


# --- reserve -----------------------------------------------------------------------------------

@dataclass
class Outcome:
    action: str
    reason: str = ""
    key: str = ""
    phase: str = ""
    changed: bool = False            # any bookkeeping file written
    queue_changed: bool = False      # research-queue.json: a closed candidate
    receipts_changed: bool = False   # work-receipts.json: a reservation or a settled receipt
    closed: str = ""                 # the work key this call closed, before re-planning once
    resolution: str = ""             # delivered | rejected, for `closed`

    def line(self) -> str:
        if self.action == rw.START and self.receipts_changed:
            head = f"reserved {self.key} ({self.phase})"
        else:
            head = " ".join(filter(None, [self.action, self.key])) + f": {self.reason}"
        return f"closed {self.closed} ({self.resolution}); then {head}" if self.closed else head


def _receipt(work: rw.Work, candidate: dict, remote: Remote, today: str) -> dict:
    prs = remote.urls(work.branch)
    receipt = {"key": work.key, "branch": work.branch, "term": work.term, "phase": work.phase,
               "state": RESERVED, "started_on": today, "source": work.source,
               "linked_work": list(dict.fromkeys([*work.linked_work, *prs]))}
    if work.source == rw.SOURCE_PAM:
        receipt.update(feed=copy.deepcopy(work.feed), candidate=copy.deepcopy(candidate))
    else:
        receipt.update(window=copy.deepcopy(work.window), metrics=copy.deepcopy(work.metrics))
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


@dataclass(frozen=True)
class _Closer:
    """What a RECONCILE closure observes with: this run's miner revision, git and clock; and the
    caller's list that receives the explicit closure result once both files are durable."""
    git: object
    mined_revision: str | None
    now: datetime
    closures: list | None = None


def reserve(demand_dir: Path, snap: dict, *, gh, today: str, repo_slug: str | None = None,
            new_pam: bool = True, git=None, mined_revision: str | None = None,
            now: datetime | None = None, close: bool = True, closures: list | None = None) -> Outcome:
    """Plan one action over the committed queue + snapshot + feed state + receipts. START appends ONE
    reservation atomically. RECONCILE verifies the linked work (jr/demand_closure.py) against `snap`,
    which must be the snapshot this run just mined at `mined_revision`; a delivered or rejected
    verdict closes the candidate in both files, then the broker re-plans ONCE so the next eligible
    candidate can START under every gate. `close=False` only reconciles (a run's later pass after a
    closure). Every other action leaves both files untouched. `closures`, when given, receives the
    closure's own Outcome the moment both files are durable, before the re-plan: a caller still
    knows of the closure if the re-plan raises, without guessing from file bytes."""
    closer = _Closer(git, mined_revision, now or datetime.now(timezone.utc), closures) if close else None
    return _reserve(Path(demand_dir), snap, gh=gh, today=today, repo_slug=repo_slug, new_pam=new_pam,
                    closer=closer)


def _writer_bytes(doc: dict) -> bytes:
    """What research_queue.write_queue puts on disk for `doc`."""
    return (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode()


def _write_closure(demand_dir: Path, closure: demand_closure.Closure, doc: dict,
                   queue_raw: bytes | None, receipts_raw: bytes | None) -> str:
    """Both files through the queue's atomic writer, under START's compare-and-swap guard extended to
    the queue. The queue closes first: a settled receipt beside a linked candidate would RECONCILE
    every run. A failed receipts write restores the queue's read bytes, but only while the queue
    still holds exactly the bytes this call wrote: a later writer's queue is never overwritten.
    Returns the problem, or "" once both are durable."""
    qpath, rpath = demand_dir / research_queue.QUEUE_NAME, demand_dir / RECEIPTS_NAME
    if _read(qpath) != queue_raw or _read(rpath) != receipts_raw:
        return f"{research_queue.QUEUE_NAME} or {RECEIPTS_NAME} changed during the run: not overwritten"
    try:
        research_queue.write_queue(closure.queue, qpath)
    except OSError as e:
        return f"{research_queue.QUEUE_NAME} write failed, both previous files kept: {e}"
    if not closure.receipts_changed:
        return ""
    try:
        research_queue.write_queue({**doc, "receipts": closure.receipts}, rpath)
    except OSError as e:
        if _read(qpath) != _writer_bytes(closure.queue):
            return (f"{RECEIPTS_NAME} write failed ({e}); {research_queue.QUEUE_NAME} changed after the "
                    "closure wrote it: not restored")
        try:
            research_queue.write_bytes(queue_raw, qpath)
        except OSError as again:
            return f"{RECEIPTS_NAME} write failed ({e}); queue left closed, restore failed: {again}"
        return f"{RECEIPTS_NAME} write failed, both previous files kept: {e}"
    return ""


def _close(demand_dir: Path, snap: dict, plan: rw.Plan, reason: str, state: dict, *, gh, today: str,
           repo_slug, new_pam: bool, closer: _Closer) -> Outcome:
    key = plan.work.key
    if len(state["remote"].prs.get(plan.work.branch, [])) > 1:      # START's duplicate check, before any verdict
        return Outcome(rw.DEFER, f"duplicate remote PRs on {plan.work.branch}: no closure", key)
    closure = demand_closure.resolve(state["queue"], state["receipts"], key, snap, gh=gh, git=closer.git,
                                     mined_revision=closer.mined_revision, today=today, now=closer.now)
    if closure.status == demand_closure.PENDING:
        return Outcome(rw.RECONCILE, f"{reason}; {closure.reason}", key)
    problem = _write_closure(demand_dir, closure, state["doc"], state["queue_raw"], state["raw"])
    if problem:
        return Outcome(rw.DEFER, problem, key)       # no closure: demand_run lands nothing for it
    if closer.closures is not None:
        closer.closures.append(Outcome(rw.DEFER, "the re-plan after the closure did not finish", changed=True,
                                       queue_changed=True, receipts_changed=closure.receipts_changed,
                                       closed=key, resolution=closure.status))
    following = _reserve(demand_dir, snap, gh=gh, today=today, repo_slug=repo_slug, new_pam=new_pam,
                         closer=None)                         # re-plan ONCE: never a second closure
    return dataclasses.replace(following, changed=True, queue_changed=True,
                               receipts_changed=following.receipts_changed or closure.receipts_changed,
                               closed=key, resolution=closure.status)


def _reserve(demand_dir: Path, snap: dict, *, gh, today: str, repo_slug: str | None,
             new_pam: bool, closer: _Closer | None) -> Outcome:
    path = Path(demand_dir) / RECEIPTS_NAME
    raw = _read(path)
    doc = _load_receipts(raw)
    if doc is None:
        return Outcome(rw.DEFER, f"unreadable {RECEIPTS_NAME} or not schema version {RECEIPTS_VERSION}: "
                                 "preserved, no new reservation")
    receipts = doc["receipts"]
    if not all(rw._readable_receipt(r) for r in receipts):
        return Outcome(rw.DEFER, "corrupt work receipt: preserved, no new reservation")
    pam_error = ""
    try:
        pam_state = pam_run.read_state(Path(demand_dir) / "pam-leads.json")
        if pam_state is not None:
            pam_leads.candidate_leads(pam_state)  # validate cache before it joins shared policy
    except (ValueError, OSError, pam_leads.FeedError):
        pam_state = None
        pam_error = "PAM state unreadable; no new feed work" if new_pam else ""
    queue_raw, queue = _load_queue(Path(demand_dir))
    view = intake(queue, snap, receipts=receipts)
    live = [r["branch"] for r in receipts if isinstance(r, dict) and isinstance(r.get("branch"), str)
            and r.get("state") not in rw.TERMINAL_STATES]
    candidates = view.get("candidates", {}).values() if isinstance(view, dict) else []
    open_work = {b for c in candidates if isinstance(c, dict) and c.get("status") != rw.STATUS_CLOSED
                 for b in [_branch(c)] if b}
    # Inspect the bounded cache's deterministic branches on the first pass. A remote
    # create can succeed before its receipt is saved; fresh-feed gating applies
    # to starting work, never to recovering that already existing identity.
    feed_branches = ({rw.branch_for(pam_leads.work_key(lead)) for lead in pam_state["leads"]}
                     if pam_state is not None else set())
    remote = remote_listing(gh, open_work | set(live) | feed_branches, repo_slug)
    recoverable = remote.open_branches() | {b for b in remote.branches if not remote.prs.get(b)}
    recovering = ({pam_leads.work_key(lead) for lead in pam_state["leads"]
                   if rw.branch_for(pam_leads.work_key(lead)) in recoverable}
                  if pam_state is not None and remote.complete else set())
    view = intake(queue, snap, pam_state=pam_state, receipts=receipts, new_pam=new_pam,
                  recovering_pam_keys=recovering)
    candidates = view.get("candidates", {}).values() if isinstance(view, dict) else []
    open_work = {b for c in candidates if isinstance(c, dict) and c.get("status") != rw.STATUS_CLOSED
                 for b in [_branch(c)] if b}
    unrecorded = remote.open_branches() - set(live)     # open remote PRs no live receipt accounts for
    prefer = unrecorded | {rw.branch_for(key) for key in recovering}
    plan = rw.plan_work(view, receipts, today, remote_complete=remote.complete, prefer=prefer)
    reason = "; ".join(filter(None, [plan.reason, remote.reason]))
    key = plan.work.key if plan.work else ""
    if plan.action == rw.RECONCILE and closer is not None:
        state = {"queue": queue, "queue_raw": queue_raw, "doc": doc, "raw": raw, "receipts": receipts,
                 "remote": remote}
        return _close(Path(demand_dir), snap, plan, reason, state, gh=gh, today=today, repo_slug=repo_slug,
                      new_pam=new_pam, closer=closer)
    if plan.action != rw.START:
        if plan.action == rw.NOOP and pam_error:
            return Outcome(rw.DEFER, pam_error)
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
    return Outcome(rw.START, plan.reason, key, plan.work.phase, changed=True, receipts_changed=True)
