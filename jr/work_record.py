"""EspAtlas Jr — the executor's write path into the demand work pair (jr/work_record.py).

SPEC-demand-work-consumer.md, Required execution path 2-4: after the daily runner reserves a work
item, an executor researches it, validates the exact identity against primary sources, links the
reviewed PR, or records a supported abandoned/rejected result. Those are the ONLY writes anyone but
the broker makes to docs/demand/research-queue.json and docs/demand/work-receipts.json, and the
broker's readers fail closed on any slip (an unreadable receipt or candidate blocks every run). So
this module is the one write path: each command re-reads both files, applies exactly one change,
re-runs the broker's own readers (research_work._readable_receipt, readable_validation, _work,
inconsistent_closures) over the whole pair and refuses to write a pair plan_work would DEFER on. The
queue is written first, through its atomic writer; a refused change leaves both files byte-identical.

Commands (CLI: python3 jr/work_record.py [--demand-dir docs/demand] [--date YYYY-MM-DD] [--dry-run] ...):
  adopt    <key>                          the work's candidate becomes a committed queue row (a PAM
                                          receipt carries its snapshot; a search receipt is rebuilt from
                                          its own provenance); closure and settle both need that row
  repair-settled <key>                    an already-settled receipt whose candidate never reached the
                                          queue gets its closed row (the pair settle would have written)
  validate <key> --json FILE              the identity/primary-source receipt: validated_by,
                                          primary_sources, expected_ids[, forbidden_ids,
                                          verification_kind, notes, verified_on]; status -> validated
  link     <key> <pr_url>                 the reviewed PR: status -> linked, receipt pr_url, phase author
  attempt  <key>                          today's try: last_attempt_on (RESUME becomes RECONCILE today)
  settle   <key> --state abandoned|rejected --reason TEXT
                                          a supported negative result: the receipt turns terminal with
                                          a resolution and its queue candidate (adopted first when
                                          absent) closes with the matching `closed` event
  check                                   the broker view of the pair, nothing written

No network, no git, no gh: the PR is recorded as given; the broker verifies it on RECONCILE.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
from pathlib import Path

import demand_broker
import pam_leads
import research_queue
import research_work as rw

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DEMAND_DIR = REPO / "docs" / "demand"
SETTLED_BY = "jr/work_record.py"
SETTLE_STATES = ("abandoned", "rejected")
_PR_URL_PREFIX = "https://github.com/"


class RecordError(ValueError):
    """A refused change: nothing was written."""


# --- the pair -----------------------------------------------------------------------------------------

def _load(demand_dir: Path) -> tuple[dict, dict]:
    demand_dir = Path(demand_dir)
    queue = research_queue.load_queue(demand_dir / research_queue.QUEUE_NAME)
    path = demand_dir / demand_broker.RECEIPTS_NAME
    if not path.exists():
        raise RecordError(f"{path.name} is absent: nothing was reserved here")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RecordError(f"{path.name} is not valid JSON: {e}") from e
    if not (isinstance(doc, dict) and doc.get("version") == 1 and isinstance(doc.get("receipts"), list)):
        raise RecordError(f"{path.name} is not a version-1 receipts file")
    return queue, doc


def _receipt(doc: dict, key: str) -> dict:
    rows = [r for r in doc["receipts"] if isinstance(r, dict) and r.get("key") == key]
    if len(rows) != 1:
        raise RecordError(f"work {key!r}: {len(rows)} receipts (expected exactly one)")
    return rows[0]


def _live(receipt: dict) -> dict:
    if receipt.get("state") in rw.TERMINAL_STATES:
        raise RecordError(f"work {receipt['key']} is not live (state {receipt['state']!r})")
    return receipt


def _candidate(queue: dict, key: str) -> tuple[str, dict]:
    found = [(k, c) for k, c in queue["candidates"].items() if isinstance(c, dict) and rw.candidate_key(c) == key]
    if len(found) != 1:
        raise RecordError(f"work {key} is not one committed queue candidate ({len(found)} found): "
                          "a PAM lead must be `adopt`ed first; a search term comes from the daily snapshot")
    return found[0]


def _guard(queue: dict, doc: dict, today: str) -> None:
    """Refuse the pair plan_work would refuse: every reader the broker runs, over the whole pair."""
    receipts = doc["receipts"]
    bad = [r.get("key") if isinstance(r, dict) else "?" for r in receipts if not rw._readable_receipt(r)]
    if bad:
        raise RecordError(f"unreadable work receipt(s) {bad}: the broker would fail closed")
    rows = rw._open_candidates(queue)
    if rows is None:
        raise RecordError("unreadable research queue")
    for c in rows:
        if not isinstance(c.get("status"), str) or c["status"] not in rw.STATUSES:
            raise RecordError(f"{c.get('term')!r}: unknown status {c.get('status')!r}")
        if c["status"] != rw.STATUS_CLOSED and rw._work(c, receipts) is None:
            raise RecordError(f"{c.get('term')!r}: missing provenance (source/window/metrics/date)")
        if c["status"] in (rw.STATUS_VALIDATED, rw.STATUS_LINKED) and rw.readable_validation(c) is None:
            raise RecordError(f"{c.get('term')!r}: status {c['status']} without a readable validation")
    inconsistent = rw.inconsistent_closures(queue, receipts)
    if inconsistent:
        raise RecordError(f"inconsistent closure of work {inconsistent}")
    one_sided = rw.one_sided_closures(queue, receipts, receipts)
    if one_sided:          # the pair the daily runner would refuse to land (2026-11-09: keeloq_mfcodes)
        raise RecordError(f"closure of work {one_sided} would be recorded on one side only")
    if rw._date(today) is None:
        raise RecordError(f"unreadable date {today!r}")


def _write(demand_dir: Path, queue: dict, doc: dict, *, queue_changed: bool, dry_run: bool = False) -> None:
    demand_dir = Path(demand_dir)
    if dry_run:
        return
    if queue_changed:                     # the queue first: a settled receipt beside a linked candidate
        research_queue.write_queue(queue, demand_dir / research_queue.QUEUE_NAME)   # would RECONCILE forever
    research_queue.write_queue(doc, demand_dir / demand_broker.RECEIPTS_NAME)


# --- commands --------------------------------------------------------------------------------------------

def _search_candidate(receipt: dict) -> dict:
    """A search receipt's candidate, rebuilt from the receipt's own provenance exactly as the broker's
    intake derives it from the daily snapshot (demand_broker._gsc_candidate): the term, its source, the
    signal window and metrics the reservation snapshotted, the lifecycle opening date. Keyed by the
    queue's term key, as research_queue.update_queue keys search rows."""
    prov = receipt.get("provenance") if isinstance(receipt.get("provenance"), dict) else {}
    opened = prov.get("opened_on") or receipt.get("started_on")
    return {"term": receipt["term"], "status": rw.STATUS_NEW, "source": receipt.get("source"),
            "first_seen": opened, "last_seen": opened,
            "window": copy.deepcopy(receipt.get("window")), "metrics": copy.deepcopy(receipt.get("metrics")),
            "linked_work": [], "history": [], "outcome": None, "closed_on": None,
            "snapshot": prov.get("snapshot") or f"docs/demand/{research_queue.QUEUE_NAME}"}


def _materialize(queue: dict, receipt: dict) -> tuple[str, dict, bool]:
    """(queue key, candidate, created) for the receipt's work: the present committed row, else a new one
    built from the receipt (a PAM receipt carries its lifecycle snapshot; a search receipt is rebuilt)."""
    key = receipt["key"]
    present = [(k, c) for k, c in queue["candidates"].items() if isinstance(c, dict) and rw.candidate_key(c) == key]
    if present:
        return present[0][0], present[0][1], False
    if receipt.get("source") == rw.SOURCE_PAM:
        candidate, qkey = copy.deepcopy(receipt.get("candidate")), key
        if not isinstance(candidate, dict) or not pam_leads.readable_work_provenance(candidate.get("feed")):
            raise RecordError(f"work {key}: the receipt carries no readable candidate snapshot")
    else:
        candidate, qkey = _search_candidate(receipt), research_queue.term_key(receipt.get("term"))
    if rw.candidate_key(candidate) != key:
        raise RecordError(f"work {key}: the rebuilt candidate keys as {rw.candidate_key(candidate)!r}, not {key!r}")
    if qkey in queue["candidates"]:
        raise RecordError(f"queue key {qkey!r} is taken by another candidate")
    queue["candidates"][qkey] = candidate
    return qkey, candidate, True


def adopt(demand_dir: Path, key: str, *, today: str, dry_run: bool = False) -> dict:
    """The work's candidate becomes a committed queue row: the closure (demand_closure.resolve) and
    `settle` both look it up there. A PAM receipt's `candidate` snapshot is adopted under its own `pam-`
    key (never the term key, where a GA4 row with the same wording would refresh it with a search window);
    a search receipt is rebuilt from its own provenance under the queue's term key. Idempotent; never
    rewrites a present row."""
    queue, doc = _load(demand_dir)
    receipt = _live(_receipt(doc, key))
    _qkey, candidate, created = _materialize(queue, receipt)
    if not created:
        return copy.deepcopy(candidate)
    if rw._work(candidate, doc["receipts"]) is None:
        raise RecordError(f"work {key}: the rebuilt candidate's provenance is not readable")
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=True, dry_run=dry_run)
    return copy.deepcopy(candidate)


def validate(demand_dir: Path, key: str, validation: dict, *, today: str, dry_run: bool = False) -> dict:
    """Record the identity/primary-source receipt on the committed candidate and promote `new` to
    `validated`. The tool fills `identity_verified`, `term_key` and the defaults (verified_on today,
    the source's default verification kind, no forbidden ids); the result must satisfy
    research_work.readable_validation and name a known kind, else nothing is written."""
    if not isinstance(validation, dict):
        raise RecordError("validation must be a JSON object")
    queue, doc = _load(demand_dir)
    _live(_receipt(doc, key))
    ckey, candidate = _candidate(queue, key)
    if candidate.get("status") not in (rw.STATUS_NEW, rw.STATUS_VALIDATED):
        raise RecordError(f"work {key}: a {candidate.get('status')!r} candidate is not validated again")
    v = {"verified_on": today, "forbidden_ids": [], "verification_kind": rw.default_verification_kind(candidate),
         **copy.deepcopy(validation),
         "identity_verified": True, "term_key": rw.term_key(candidate.get("term"))}
    if v["verification_kind"] not in rw._KIND_CHECKS:
        raise RecordError(f"unknown verification kind {v['verification_kind']!r}: one of {sorted(rw._KIND_CHECKS)}")
    probe = {**candidate, "validation": v}
    if rw.readable_validation(probe) is None:
        raise RecordError("validation is not readable: it needs validated_by, verified_on (YYYY-MM-DD), "
                          "non-empty primary_sources and expected_ids, and forbidden_ids disjoint from them")
    candidate.update(validation=v, status=rw.STATUS_VALIDATED)
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=True, dry_run=dry_run)
    return copy.deepcopy(candidate)


def link(demand_dir: Path, key: str, pr_url: str, *, today: str, dry_run: bool = False) -> dict:
    """Record the one reviewed PR on both files: candidate `linked` with the url in linked_work, receipt
    pr_url + linked_work + phase author + last_attempt_on today. A second, different PR is refused."""
    if not (isinstance(pr_url, str) and pr_url.startswith(_PR_URL_PREFIX) and "/pull/" in pr_url
            and pr_url.rsplit("/", 1)[-1].isdigit()):
        raise RecordError(f"{pr_url!r} is not a GitHub pull request url")
    queue, doc = _load(demand_dir)
    receipt = _live(_receipt(doc, key))
    ckey, candidate = _candidate(queue, key)
    if candidate.get("status") not in (rw.STATUS_VALIDATED, rw.STATUS_LINKED) or rw.readable_validation(candidate) is None:
        raise RecordError(f"work {key}: a PR links only to a validated candidate (this one is "
                          f"{candidate.get('status')!r})")
    known = {u for u in (candidate.get("linked_work") or []) if rw._text(u)} | ({receipt["pr_url"]} if "pr_url" in receipt else set())
    if known - {pr_url}:
        raise RecordError(f"work {key} already links {sorted(known - {pr_url})}: one PR per work item")
    links = list(candidate.get("linked_work") or [])
    if pr_url not in links:
        links.append(pr_url)
    candidate.update(status=rw.STATUS_LINKED, linked_work=links)
    receipt_links = list(receipt.get("linked_work") or [])
    if pr_url not in receipt_links:
        receipt_links.append(pr_url)
    receipt.update(pr_url=pr_url, linked_work=receipt_links, phase=rw.PHASE_AUTHOR, last_attempt_on=today)
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=True, dry_run=dry_run)
    return copy.deepcopy(candidate)


def attempt(demand_dir: Path, key: str, *, today: str, dry_run: bool = False) -> dict:
    """Stamp today's attempt on the live receipt: the broker then RECONCILEs instead of RESUMEs today."""
    queue, doc = _load(demand_dir)
    receipt = _live(_receipt(doc, key))
    receipt["last_attempt_on"] = today
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=False, dry_run=dry_run)
    return copy.deepcopy(receipt)


def _close_candidate(candidate: dict, *, key: str, state: str, reason: str, today: str) -> None:
    history = {"event": "closed", "date": today, "resolution": state, "work": key, "reason": reason}
    if candidate.get("outcome") is not None:
        history["previous_outcome"] = copy.deepcopy(candidate["outcome"])
    candidate.update(status=rw.STATUS_CLOSED, outcome={"status": state, "reason": reason}, closed_on=today)
    candidate["history"] = [*(candidate.get("history") or []), history]


def settle(demand_dir: Path, key: str, *, state: str, reason: str, today: str, dry_run: bool = False) -> dict:
    """A supported negative result, recorded on BOTH sides in one guarded write, exactly the pair a broker
    closure leaves: the live receipt becomes `abandoned` or `rejected` with a resolution naming the reason,
    and its queue candidate — adopted first when the queue has none, a search term living only in the
    daily snapshot included — closes with the outcome and a `closed` history event naming the work. The
    daily runner refuses to land a resolution without that event (2026-11-09: keeloq_mfcodes)."""
    if state not in SETTLE_STATES:
        raise RecordError(f"state must be one of {SETTLE_STATES}, not {state!r} (delivered is the broker's verdict)")
    if not (isinstance(reason, str) and reason.strip()):
        raise RecordError("a settled receipt needs a reason")
    reason = reason.strip()
    queue, doc = _load(demand_dir)
    receipt = _live(_receipt(doc, key))
    _qkey, candidate, _created = _materialize(queue, receipt)
    if candidate.get("status") != rw.STATUS_CLOSED:
        _close_candidate(candidate, key=key, state=state, reason=reason, today=today)
    receipt.update(state=state, resolution={"status": state, "reason": reason, "closed_on": today,
                                            "evidence": {"settled_by": SETTLED_BY}})
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=True, dry_run=dry_run)
    return copy.deepcopy(receipt)


def repair_settled(demand_dir: Path, key: str, *, today: str, dry_run: bool = False) -> dict:
    """An already-settled receipt (terminal, with a resolution) whose candidate never reached the queue
    gets the closed row `settle` would have written, from the resolution's own status, reason and
    closed_on. Nothing else changes; a receipt that already has its row is a no-op."""
    queue, doc = _load(demand_dir)
    receipt = _receipt(doc, key)
    resolution = receipt.get("resolution")
    if receipt.get("state") not in rw.TERMINAL_STATES or not isinstance(resolution, dict):
        raise RecordError(f"work {key} is not a settled receipt (state {receipt.get('state')!r}): nothing to repair")
    _qkey, candidate, created = _materialize(queue, receipt)
    if not created and candidate.get("status") == rw.STATUS_CLOSED:
        return copy.deepcopy(candidate)
    state = resolution.get("status") if resolution.get("status") in (*SETTLE_STATES, "delivered") else receipt["state"]
    _close_candidate(candidate, key=key, state=state, reason=str(resolution.get("reason") or "settled"),
                     today=str(resolution.get("closed_on") or today))
    _guard(queue, doc, today)
    _write(demand_dir, queue, doc, queue_changed=True, dry_run=dry_run)
    return copy.deepcopy(candidate)


def check(demand_dir: Path, *, today: str) -> dict:
    """The broker's view of the pair, nothing written: the fail-closed problems (empty when the pair
    is clean), the live work keys and every candidate's status."""
    queue, doc = _load(demand_dir)
    problems = []
    try:
        _guard(queue, doc, today)
    except RecordError as e:
        problems.append(str(e))
    live = sorted(r["key"] for r in doc["receipts"] if isinstance(r, dict) and r.get("state") not in rw.TERMINAL_STATES)
    return {"problems": problems, "live": live,
            "candidates": {k: c.get("status") for k, c in queue["candidates"].items() if isinstance(c, dict)}}


# --- CLI --------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """The CLI. `--date` and `--dry-run` are accepted both before and after the subcommand (the
    executor prompt writes them after it; a global option is the usual place), with one meaning."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--date", default=argparse.SUPPRESS, help="UTC date (YYYY-MM-DD; default today)")
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                        help="apply and guard, print the result, write nothing")
    ap = argparse.ArgumentParser(description="EspAtlas Jr demand work records — the executor's write path",
                                 parents=[common])     # no set_defaults here: parents share Action objects
    ap.add_argument("--demand-dir", default=str(DEFAULT_DEMAND_DIR), help="docs/demand of the checkout to record in")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("adopt", parents=[common]).add_argument("key")
    p = sub.add_parser("validate", parents=[common])
    p.add_argument("key")
    p.add_argument("--json", required=True, help="file with the validation object")
    p = sub.add_parser("link", parents=[common])
    p.add_argument("key")
    p.add_argument("pr_url")
    sub.add_parser("attempt", parents=[common]).add_argument("key")
    p = sub.add_parser("settle", parents=[common])
    p.add_argument("key")
    p.add_argument("--state", required=True, choices=SETTLE_STATES)
    p.add_argument("--reason", required=True)
    sub.add_parser("repair-settled", parents=[common]).add_argument("key")
    sub.add_parser("check", parents=[common])
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.date = getattr(args, "date", None) or dt.datetime.now(dt.timezone.utc).date().isoformat()
    args.dry_run = getattr(args, "dry_run", False)
    d = Path(args.demand_dir)
    try:
        if args.cmd == "check":
            result = check(d, today=args.date)
        elif args.cmd == "adopt":
            result = adopt(d, args.key, today=args.date, dry_run=args.dry_run)
        elif args.cmd == "validate":
            try:
                validation = json.loads(Path(args.json).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise RecordError(f"cannot read validation JSON {args.json}: {e}") from e
            result = validate(d, args.key, validation, today=args.date, dry_run=args.dry_run)
        elif args.cmd == "link":
            result = link(d, args.key, args.pr_url, today=args.date, dry_run=args.dry_run)
        elif args.cmd == "attempt":
            result = attempt(d, args.key, today=args.date, dry_run=args.dry_run)
        elif args.cmd == "repair-settled":
            result = repair_settled(d, args.key, today=args.date, dry_run=args.dry_run)
        else:
            result = settle(d, args.key, state=args.state, reason=args.reason, today=args.date, dry_run=args.dry_run)
    except (RecordError, ValueError, KeyError, OSError) as e:
        print(f"work-record: {e}", file=sys.stderr)
        return 1
    mode = ("read-only" if args.cmd == "check"
            else "dry-run, nothing written" if args.dry_run else "written")
    summary = result.get("status") or result.get("state") or ""
    print(f"work-record: {args.cmd} {getattr(args, 'key', '')} → {summary} ({mode})".replace("  ", " "))
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
