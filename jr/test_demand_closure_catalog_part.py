"""Autonomous RECONCILE closure of `catalog_part` work: a missing BOARD verified at the exact public
part endpoint (SPEC-demand-work-consumer.md, Verification must match the actual defect; decision
2026-11-08).

Why a third kind: `catalog_search` demands that /api/search?q=<term> returns exactly the expected ids.
That holds for a bare SKU (fnk0104s -> 1 id) and never for a PAM lead's name hint ("Arduino Nano
ESP32" -> 132 ids from the fuzzy ranker), so a merged, deployed PAM board could never close. Here the
broker GETs /api/status for the deployed revision, /api/parts/<id> for every expected id (200 and the
body's own `id`) and every forbidden id (404), /api/search?q=<expected id> (the id among the results
and that response's own revision), then /api/status again; every revision must agree.
research_work.verify_resolution stays the only judge. Every read goes through an injected fake getter.

Run: cd jr && python3 -m pytest test_demand_closure_catalog_part.py -v
"""
from __future__ import annotations

import json
import urllib.parse

import pytest

import demand_broker as broker
import demand_closure
import research_work as rw
from test_demand_broker import SLUG
from test_demand_closure import (KEY, MERGE_SHA, NEXT_DAY, NEXT_NOW, PR_URL, QUEUE, RECEIPTS, SNAP,
                                 demand_dir, doc, fnk, gh_for, git_for, own_receipt, queue_bytes)
from test_demand_closure_live_search import DEPLOYED, STATUS_URL, status_body

EXPECTED = ["freenove-fnk0104s"]
FORBIDDEN = ["freenove-fnk0104a", "freenove-fnk0104b"]
RECEIPT_FIELDS = {"kind", "http", "deployment", "ids", "missing", "forbidden_hits", "query", "checked_at",
                  "merge_sha", "contains_merge"}


def parts_url(part_id):
    return f"https://esp-atlas.com/api/parts/{urllib.parse.quote(part_id, safe='')}"


def search_url(part_id):
    return "https://esp-atlas.com/api/search?" + urllib.parse.urlencode({"q": part_id})


def part_body(part_id):
    return json.dumps({"id": part_id, "type": "board", "name": part_id.upper()}).encode()


def search_body(ids, revision=DEPLOYED):
    body = {"results": [{"id": i, "type": "board", "name": i} for i in ids]}
    if revision is not ...:
        body["revision"] = revision
    return json.dumps(body).encode()


class Getter:
    """A fake of demand_closure.default_fetch: url -> (http status, body bytes); records every url.
    `parts` maps a part id to its answer (default: 200 for expected, 404 for forbidden); `searches`
    maps a part id to its /api/search answer (default: the id alone at the deployed revision)."""

    def __init__(self, *, statuses=None, parts=None, searches=None):
        self.statuses = list(statuses or [(200, status_body())])
        self.parts = {**{i: (200, part_body(i)) for i in EXPECTED}, **{i: (404, b"") for i in FORBIDDEN},
                      **(parts or {})}
        self.searches = {**{i: (200, search_body([i])) for i in EXPECTED}, **(searches or {})}
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url == STATUS_URL:
            answer = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        elif url.startswith("https://esp-atlas.com/api/parts/"):
            answer = self.parts[urllib.parse.unquote(url.rsplit("/", 1)[1])]
        elif url.startswith("https://esp-atlas.com/api/search?"):
            answer = self.searches[urllib.parse.parse_qs(url.split("?", 1)[1])["q"][0]]
        else:
            raise AssertionError(f"unexpected live read {url}")
        if isinstance(answer, BaseException):
            raise answer
        return answer


def catalog_part_dir(tmp_path, **validation):
    def kind(c):
        c["validation"].update({"verification_kind": "catalog_part", "expected_ids": EXPECTED,
                                "forbidden_ids": FORBIDDEN, **validation})
    return demand_dir(tmp_path, queue=queue_bytes(kind))


def live_reserve(d, fetch, **kw):
    return broker.reserve(d, {"date": NEXT_DAY, "items": []}, gh=kw.pop("gh", gh_for()),
                          git=kw.pop("git", git_for()), repo_slug=SLUG, today=NEXT_DAY,
                          now=NEXT_NOW, mined_revision=None, new_pam=False, fetch=fetch, **kw)


def candidate(**validation):
    def kind(c):
        c["validation"].update({"verification_kind": "catalog_part", "expected_ids": EXPECTED,
                                "forbidden_ids": FORBIDDEN, **validation})
    return json.loads(queue_bytes(kind))["candidates"]["fnk0104s"]


PR = {"url": PR_URL, "state": "merged", "merged": True, "merge_sha": MERGE_SHA, "merged_at": "2026-11-06T09:19:44Z"}


# --- delivered ----------------------------------------------------------------------------------

def test_the_kind_exists_and_is_pams_default():
    assert rw.KIND_CATALOG_PART == "catalog_part"
    assert rw.default_verification_kind({"source": rw.SOURCE_PAM}) == rw.KIND_CATALOG_PART
    assert rw.default_verification_kind({"source": "gsc_query"}) == rw.KIND_CATALOG_SEARCH


def test_every_expected_part_present_and_every_forbidden_absent_closes_delivered(tmp_path):
    d = catalog_part_dir(tmp_path)
    fetch, git = Getter(), git_for()
    out = live_reserve(d, fetch, git=git)

    assert out.closed == KEY and out.resolution == "delivered" and out.changed is True
    assert fetch.calls == [STATUS_URL, parts_url("freenove-fnk0104s"), parts_url("freenove-fnk0104a"),
                           parts_url("freenove-fnk0104b"), search_url("freenove-fnk0104s"), STATUS_URL]
    assert ("merge-base", "--is-ancestor", MERGE_SHA, DEPLOYED) in git.calls

    c = fnk(d)
    assert c["status"] == "closed" and c["closed_on"] == NEXT_DAY
    ev = c["outcome"]
    assert ev["verification_kind"] == "catalog_part" and ev["query"] == "fnk0104s"
    assert ev["http"] == 200 and ev["deployment"] == DEPLOYED and ev["ids"] == EXPECTED
    assert ev["missing"] == [] and ev["forbidden_hits"] == []
    assert ev["merge_sha"] == MERGE_SHA and ev["pr_url"] == PR_URL
    assert c["history"][-1]["deployment"] == DEPLOYED and c["history"][-1]["resolution"] == "delivered"
    r = own_receipt(d)
    assert r["state"] == "delivered" and r["resolution"]["evidence"] == ev


def test_the_receipt_carries_exactly_the_catalog_part_fields():
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(),
                                          now=NEXT_NOW, fetch=Getter())
    assert why == ""
    assert set(receipt) == RECEIPT_FIELDS
    assert receipt["kind"] == "catalog_part" and receipt["ids"] == EXPECTED
    assert receipt["missing"] == [] and receipt["forbidden_hits"] == [] and receipt["contains_merge"] is True
    assert rw.verify_resolution(candidate(), PR, receipt, NEXT_DAY).status == "delivered"


def test_no_forbidden_ids_means_no_forbidden_reads():
    fetch = Getter()
    receipt, why = demand_closure.observe(candidate(forbidden_ids=[]), PR, {}, mined_revision=None,
                                          git=git_for(), now=NEXT_NOW, fetch=fetch)
    assert why == "" and receipt["forbidden_hits"] == []
    assert fetch.calls == [STATUS_URL, parts_url("freenove-fnk0104s"), search_url("freenove-fnk0104s"), STATUS_URL]


# --- pending: the postcondition is not there yet ---------------------------------------------------

def test_an_expected_part_still_404_stays_pending_and_writes_nothing(tmp_path):
    d = catalog_part_dir(tmp_path)
    before = ((d / QUEUE).read_bytes(), (d / RECEIPTS).read_bytes())
    out = live_reserve(d, Getter(parts={"freenove-fnk0104s": (404, b"")}))
    assert out.closed == "" and out.action == rw.RECONCILE
    assert "lacks expected parts" in out.reason and "freenove-fnk0104s" in out.reason
    assert ((d / QUEUE).read_bytes(), (d / RECEIPTS).read_bytes()) == before


def test_a_forbidden_sibling_now_present_stays_pending(tmp_path):
    d = catalog_part_dir(tmp_path)
    out = live_reserve(d, Getter(parts={"freenove-fnk0104a": (200, part_body("freenove-fnk0104a"))}))
    assert out.closed == "" and "forbidden" in out.reason and "freenove-fnk0104a" in out.reason


def test_a_part_body_naming_another_id_is_missing_not_present():
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=Getter(parts={"freenove-fnk0104s": (200, part_body("other"))}))
    assert why == "" and receipt["missing"] == ["freenove-fnk0104s"] and receipt["ids"] == []
    assert rw.verify_resolution(candidate(), PR, receipt, NEXT_DAY).status == "pending"


def test_a_search_by_id_that_does_not_list_the_part_is_missing():
    fetch = Getter(searches={"freenove-fnk0104s": (200, search_body(["freenove-fnk0104a"]))})
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=fetch)
    assert why == "" and receipt["missing"] == ["freenove-fnk0104s"]
    assert rw.verify_resolution(candidate(), PR, receipt, NEXT_DAY).status == "pending"


def test_a_deployment_not_containing_the_merge_stays_pending():
    receipt, _ = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(ancestor_rc=1),
                                        now=NEXT_NOW, fetch=Getter())
    assert receipt["contains_merge"] is False
    res = rw.verify_resolution(candidate(), PR, receipt, NEXT_DAY)
    assert res.status == "pending" and "containing this merge" in res.reason


# --- unread: no receipt is built --------------------------------------------------------------------

@pytest.mark.parametrize("statuses", [
    [(200, status_body()), (200, status_body("1" * 40))],          # the deployment changed mid-check
    [(503, b"")],
    [(200, status_body(revision=...))],
])
def test_an_unreadable_or_moving_deployment_builds_no_receipt(statuses):
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=Getter(statuses=statuses))
    assert receipt is None and "catalog_part live check" in why


@pytest.mark.parametrize("answer", [(500, b""), (200, b"not json"), OSError("connection reset")])
def test_a_part_read_that_is_neither_200_nor_404_builds_no_receipt(answer):
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=Getter(parts={"freenove-fnk0104s": answer}))
    assert receipt is None and "catalog_part live check" in why


def test_a_search_answer_at_another_revision_builds_no_receipt():
    fetch = Getter(searches={"freenove-fnk0104s": (200, search_body(EXPECTED, revision="2" * 40))})
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=fetch)
    assert receipt is None and "revision" in why


def test_without_an_injected_getter_nothing_is_invented():
    receipt, why = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                          fetch=None)
    assert receipt is None and "none is invented" in why


def test_an_unmerged_pr_is_never_checked_live():
    fetch = Getter()
    receipt, why = demand_closure.observe(candidate(), {**PR, "merged": False, "state": "open"}, {},
                                          mined_revision=None, git=git_for(), now=NEXT_NOW, fetch=fetch)
    assert receipt is None and fetch.calls == []


# --- the judge is strict about the kind ---------------------------------------------------------------

def test_a_catalog_search_receipt_does_not_satisfy_catalog_part_work():
    receipt = {"http": 200, "deployment": DEPLOYED, "ids": EXPECTED, "query": "fnk0104s",
               "checked_at": NEXT_NOW.isoformat(), "merge_sha": MERGE_SHA, "contains_merge": True}
    res = rw.verify_resolution(candidate(), PR, receipt, NEXT_DAY)
    assert res.status == "pending" and "not a catalog_part verification" in res.reason


def test_a_catalog_part_receipt_does_not_satisfy_catalog_search_work():
    receipt, _ = demand_closure.observe(candidate(), PR, {}, mined_revision=None, git=git_for(), now=NEXT_NOW,
                                        fetch=Getter())
    search_candidate = json.loads(queue_bytes(lambda c: c["validation"].update(
        verification_kind="catalog_search")))["candidates"]["fnk0104s"]
    res = rw.verify_resolution(search_candidate, PR, receipt, NEXT_DAY)
    assert res.status == "pending" and "not a catalog_search verification" in res.reason
