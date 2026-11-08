"""EspAtlas Jr — autonomous RECONCILE closure for the demand work broker
(SPEC-demand-work-consumer.md, Required execution path step 4 and Outcome evidence).

When research_work.plan_work answers RECONCILE for linked work, `resolve` reads the linked PR
through the injected `gh`, builds the observation receipt the validation's verification kind names,
and hands both to research_work.verify_resolution, unchanged. Only its verdict decides:

- delivered / rejected: `resolve` returns the committed queue and receipts with the candidate
  closed (its earlier history kept, one entry appended) and the work receipt settled; the broker
  writes both files with its compare-and-swap guard;
- pending: nothing to write, only the reason.

A `demand_resolution` observation is THIS run's miner result: the snapshot it just mined, at the
catalog revision it mined (`mined_revision`), whose ancestry of the merge is asked of the injected
`git`. A `catalog_search` observation is a live public search through the injected `fetch` getter:
GET /api/status for the full deployed revision, GET /api/search?q=<term> for the exact ids it
returns, then /api/status again, so both reads name one deployment; `git merge-base --is-ancestor`
says whether that revision contains the merge. Any unreadable answer (a missing, short or changed
revision, a non-200, a timeout, unreadable JSON) is no receipt at all, so the work stays pending;
without a getter no live search is invented. Never /api/intent.

Pure apart from the injected gh/git/fetch calls: inputs are never mutated, no file is written.
"""
from __future__ import annotations

import copy
import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import research_work as rw

DELIVERED, REJECTED, PENDING = "delivered", "rejected", "pending"
PR_FIELDS = "url,state,mergedAt,mergeCommit"
PR_STATES = {"OPEN", "CLOSED", "MERGED"}
_SHA_RE = re.compile(r"[0-9a-f]{7,40}")      # never hand git an option-looking or arbitrary string
DEMAND_RELDIR = "docs/demand"
SITE = "https://esp-atlas.com"
STATUS_URL = f"{SITE}/api/status"
FETCH_TIMEOUT_S = 10
_REVISION_RE = re.compile(r"[0-9a-f]{40}")   # only the full deployed SHA: a short one may be ambiguous
_urlopen = urllib.request.urlopen            # default_fetch's only network effect (jr tests keep it offline)


@dataclass(frozen=True)
class Closure:
    status: str                       # delivered | rejected | pending
    reason: str
    queue: dict | None = None         # the committed queue with the candidate closed
    receipts: list | None = None      # the receipts with this work settled
    receipts_changed: bool = False


def _pending(reason: str) -> Closure:
    return Closure(PENDING, reason)


# --- observation -------------------------------------------------------------------------------

def read_pr(gh, url: str) -> dict | None:
    """The linked PR in verify_resolution's shape, or None when gh fails or answers unreadably."""
    p = gh("pr", "view", url, "--json", PR_FIELDS)
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        pr = json.loads(getattr(p, "stdout", "") or "")
    except ValueError:
        return None
    if not isinstance(pr, dict) or pr.get("url") != url or pr.get("state") not in PR_STATES:
        return None
    commit = pr.get("mergeCommit") if isinstance(pr.get("mergeCommit"), dict) else {}
    return {"url": url, "state": pr["state"].lower(), "merged": pr["state"] == "MERGED",
            "merge_sha": commit.get("oid"), "merged_at": pr.get("mergedAt")}


def contains_merge(git, merge_sha, revision) -> bool:
    """True only when git says the merge is an ancestor of the mined revision; unknown is False."""
    if git is None or not all(isinstance(s, str) and _SHA_RE.fullmatch(s) for s in (merge_sha, revision)):
        return False
    return getattr(git("merge-base", "--is-ancestor", merge_sha, revision), "returncode", 1) == 0


def _miner_receipt(candidate: dict, pr: dict, snap: dict, *, mined_revision, git,
                   now: datetime) -> tuple[dict | None, str]:
    """This run's miner result for the term, or (None, why). exit_code 0 is recorded only because
    the broker runs after a successful mine (demand_run passes `mined_revision` only then)."""
    if not (isinstance(mined_revision, str) and _SHA_RE.fullmatch(mined_revision)):
        return None, "no successful miner run at a known revision this invocation"
    # The item's own term only: a merged wording (`raw_terms`) shares the group's `resolved`, which
    # describes the group's first wording, not necessarily this one. Unmatched stays pending.
    term = rw.term_key(candidate.get("term"))
    items = [i for i in (snap or {}).get("items") or [] if isinstance(i, dict) and rw.term_key(i.get("term")) == term]
    if len(items) != 1:
        return None, f"this run's snapshot has no item (or several) for {candidate.get('term')!r}"
    item = items[0]
    return {"kind": rw.KIND_DEMAND_RESOLUTION, "query": candidate["term"], "exit_code": 0,
            "mined_revision": mined_revision, "merge_sha": pr.get("merge_sha"),
            "contains_merge": contains_merge(git, pr.get("merge_sha"), mined_revision),
            "resolved": copy.deepcopy(item.get("resolved")), "gap": item.get("gap"),
            "checked_at": now.isoformat()}, ""


def default_fetch(url: str) -> tuple[int, bytes]:
    """GET `url` with a short timeout and no cache: (HTTP status, body). An HTTP error status is
    answered, not raised; a network failure or timeout raises (OSError), as urllib does."""
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "esp-atlas-jr"})
    try:
        with _urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def search_url(term: str) -> str:
    return f"{SITE}/api/search?{urllib.parse.urlencode({'q': term})}"


class _Unread(Exception):
    """A live read that proves nothing: the receipt is not built."""


def _get_json(fetch, url: str):
    try:
        status, body = fetch(url)
    except (OSError, ValueError, TypeError, http.client.HTTPException) as e:   # incl. a malformed answer
        raise _Unread(f"GET {url} failed: {e}") from e
    if status != 200:
        raise _Unread(f"GET {url} answered HTTP {status}")
    try:
        return json.loads(body)
    except (ValueError, TypeError) as e:
        raise _Unread(f"GET {url} answered unreadable JSON") from e


def _deployed_revision(fetch) -> str:
    doc = _get_json(fetch, STATUS_URL)
    components = doc.get("components") if isinstance(doc, dict) else None
    deploys = [c for c in components if isinstance(c, dict) and c.get("name") == "Deploy"] \
        if isinstance(components, list) else []
    revision = deploys[0].get("revision") if len(deploys) == 1 else None
    if not (isinstance(revision, str) and _REVISION_RE.fullmatch(revision)):
        raise _Unread("deployed revision unreadable: /api/status serves no full 40-hex Deploy revision")
    return revision


def _search_ids(fetch, term: str, expected_revision: str) -> list[str]:
    url = search_url(term)
    doc = _get_json(fetch, url)
    results = doc.get("results") if isinstance(doc, dict) else None
    if not (isinstance(results, list) and all(isinstance(r, dict) and rw._text(r.get("id")) for r in results)):
        raise _Unread(f"GET {url} answered unreadable search results")
    revision = doc.get("revision")
    if not (isinstance(revision, str) and _REVISION_RE.fullmatch(revision)):
        raise _Unread(f"GET {url} answered unreadable search revision")
    if revision != expected_revision:
        raise _Unread(f"GET {url} search revision differs from /api/status")
    return [r["id"] for r in results]


def parts_url(part_id: str) -> str:
    return f"{SITE}/api/parts/{urllib.parse.quote(part_id, safe='')}"


def _part_present(fetch, part_id: str) -> bool:
    """Whether the public part endpoint serves `part_id` as itself: 200 with that `id` in its body is
    present, 404 is absent (a readable answer, not a failure), anything else proves nothing."""
    url = parts_url(part_id)
    try:
        status, body = fetch(url)
    except (OSError, ValueError, TypeError, http.client.HTTPException) as e:
        raise _Unread(f"GET {url} failed: {e}") from e
    if status == 404:
        return False
    if status != 200:
        raise _Unread(f"GET {url} answered HTTP {status}")
    try:
        doc = json.loads(body)
    except (ValueError, TypeError) as e:
        raise _Unread(f"GET {url} answered unreadable JSON") from e
    return isinstance(doc, dict) and doc.get("id") == part_id


def _catalog_part_receipt(candidate: dict, validation: dict, pr: dict, *, fetch, git,
                          now: datetime) -> tuple[dict | None, str]:
    """The catalog_part receipt verify_resolution judges, or (None, why): a missing BOARD is verified
    at the exact public part endpoint, never through the fuzzy search of its name. Bracketed by two
    /api/status reads naming the same full revision: every expected id must be served by
    /api/parts/<id> (200, its own `id`) AND listed by /api/search?q=<id> at that same revision; every
    forbidden sibling must answer 404. A 404 on an expected id or a 200 on a forbidden one is a
    readable "not yet" (recorded, pending); any other failure builds no receipt."""
    if fetch is None:
        return None, ("catalog_part verification needs a live public catalog getter; none was injected, "
                      "so none is invented")
    expected = [i for i in (validation.get("expected_ids") or []) if rw._text(i)]
    forbidden = list(rw._forbidden_ids(validation) or [])
    if not expected or not rw._text(candidate.get("term")):
        return None, "catalog_part live check: no readable expected ids"
    try:
        revision = _deployed_revision(fetch)
        present = [i for i in expected if _part_present(fetch, i)]
        hits = [i for i in forbidden if _part_present(fetch, i)]
        present = [i for i in present if i in _search_ids(fetch, i, revision)]
        if _deployed_revision(fetch) != revision:
            raise _Unread("deployed revision changed during the live check")
    except _Unread as e:
        return None, f"catalog_part live check: {e}"
    return {"kind": rw.KIND_CATALOG_PART, "http": 200, "deployment": revision, "ids": present,
            "missing": [i for i in expected if i not in present], "forbidden_hits": hits,
            "query": candidate["term"], "checked_at": now.astimezone(timezone.utc).isoformat(),
            "merge_sha": pr.get("merge_sha"), "contains_merge": contains_merge(git, pr.get("merge_sha"), revision)}, ""


def _live_search_receipt(candidate: dict, pr: dict, *, fetch, git, now: datetime) -> tuple[dict | None, str]:
    """The catalog_search receipt verify_resolution judges, or (None, why). The search is bracketed by
    two /api/status reads naming the same full revision, so its ids came from that deployment."""
    if fetch is None:
        return None, ("catalog_search verification needs a live public search getter; none was injected, "
                      "so none is invented")
    if not rw._text(candidate.get("term")):
        return None, "catalog_search live check: no readable term to search"
    try:
        revision = _deployed_revision(fetch)
        ids = _search_ids(fetch, candidate["term"], revision)
        if _deployed_revision(fetch) != revision:
            raise _Unread("deployed revision changed during the live search")
    except _Unread as e:
        return None, f"catalog_search live check: {e}"
    return {"http": 200, "deployment": revision, "ids": ids, "query": candidate["term"],
            "checked_at": now.astimezone(timezone.utc).isoformat(), "merge_sha": pr.get("merge_sha"),
            "contains_merge": contains_merge(git, pr.get("merge_sha"), revision)}, ""


def observe(candidate: dict, pr: dict, snap: dict, *, mined_revision, git, now: datetime,
            fetch=None) -> tuple[dict | None, str]:
    """The observation receipt for the validation's verification kind, or (None, why)."""
    validation = rw.readable_validation(candidate) or {}
    kind = validation.get("verification_kind", rw.KIND_CATALOG_SEARCH)
    if kind not in rw._KIND_CHECKS or not pr.get("merged"):
        return None, ""                 # verify_resolution names the problem
    if kind == rw.KIND_CATALOG_SEARCH:
        return _live_search_receipt(candidate, pr, fetch=fetch, git=git, now=now)
    if kind == rw.KIND_CATALOG_PART:
        return _catalog_part_receipt(candidate, validation, pr, fetch=fetch, git=git, now=now)
    return _miner_receipt(candidate, pr, snap, mined_revision=mined_revision, git=git, now=now)


# --- the closed records ------------------------------------------------------------------------

def _linked_pr(candidate: dict, own: list[dict]) -> tuple[str | None, str]:
    links = candidate.get("linked_work") if isinstance(candidate.get("linked_work"), list) else []
    urls = list(dict.fromkeys([r["pr_url"] for r in own if "pr_url" in r] + [u for u in links if rw._text(u)]))
    if len(urls) != 1:
        return None, f"{len(urls)} linked PRs: no single PR to verify"
    return urls[0], ""


def _closed(queue: dict, ckey: str, receipts: list, key: str, record: dict, history: dict,
            receipt_state: str, resolution: dict) -> Closure:
    queue = copy.deepcopy(queue)
    c = queue["candidates"][ckey]
    if c.get("outcome") is not None:
        history["previous_outcome"] = copy.deepcopy(c["outcome"])   # a recorded outcome is kept, not lost
    c.update(status=rw.STATUS_CLOSED, outcome=record, closed_on=resolution["closed_on"])
    c["history"] = [*(c.get("history") or []), history]          # earlier history is never rewritten
    settled = [({**copy.deepcopy(r), "state": receipt_state, "resolution": copy.deepcopy(resolution)}
                if r["key"] == key and r["state"] not in rw.TERMINAL_STATES else r) for r in receipts]
    return Closure(resolution["status"], resolution["reason"], queue, settled, settled != list(receipts))


def resolve(queue: dict, receipts: list, key: str, snap: dict, *, gh, git, mined_revision,
            today: str, now: datetime, fetch=None) -> Closure:
    """Verify the linked work `key` and, when delivered or rejected, return the closed records."""
    found = [(k, c) for k, c in (queue.get("candidates") or {}).items()
             if isinstance(c, dict) and rw.candidate_key(c) == key]
    if len(found) != 1:
        return _pending("work is not one committed queue candidate: nothing to close")
    ckey, candidate = found[0]
    if candidate.get("status") != rw.STATUS_LINKED:
        return _pending("candidate is not linked work yet: nothing to verify")
    own = [r for r in receipts if r["key"] == key]
    url, why = _linked_pr(candidate, own)
    if url is None:
        return _pending(why)
    pr = read_pr(gh, url)
    if pr is None:
        return _pending(f"linked PR {url} unreadable: merge state deferred")
    observed, why = observe(candidate, pr, snap, mined_revision=mined_revision, git=git, now=now, fetch=fetch)
    res = rw.verify_resolution(candidate, pr, observed, today, work_receipts=receipts)
    if res.status == PENDING:
        return _pending("; ".join(filter(None, [why, res.reason])))
    history = {"event": "closed", "date": today, "resolution": res.status, "work": key, "pr_url": url}
    if res.status == DELIVERED:
        history["merge_sha"] = pr["merge_sha"]
        if "deployment" in res.evidence:           # catalog_search: the deployment searched, not a snapshot
            history["deployment"] = res.evidence["deployment"]
        else:
            history["snapshot"] = f"{DEMAND_RELDIR}/{snap.get('date')}.json"
        resolution = {"status": DELIVERED, "reason": res.reason, "closed_on": res.closed_on,
                      "evidence": copy.deepcopy(res.evidence)}
        return _closed(queue, ckey, receipts, key, copy.deepcopy(res.evidence), history, DELIVERED, resolution)
    evidence = {"pr_url": url, "pr_state": pr["state"], "merged": False, "checked_at": now.isoformat()}
    history["reason"] = res.reason
    resolution = {"status": REJECTED, "reason": res.reason, "closed_on": today, "evidence": evidence}
    return _closed(queue, ckey, receipts, key, {"status": REJECTED, "reason": res.reason, **evidence},
                   history, REJECTED, resolution)
