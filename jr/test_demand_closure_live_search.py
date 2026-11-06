"""Autonomous RECONCILE closure of `catalog_search` work: the live public search receipt
(SPEC-demand-work-consumer.md, Autonomous RECONCILE closure).

The broker GETs /api/status for the full deployed revision, the exact ids /api/search returns for the
term, then /api/status again; `git merge-base --is-ancestor <merge> <revision>` says whether that
deployment contains the merge. research_work.verify_resolution stays the only judge. Every network
read goes through an injected fake getter: no test here reaches the network.

Run: cd jr && python3 -m pytest test_demand_closure_live_search.py -v
"""
from __future__ import annotations

import json
import socket
import urllib.error
from datetime import timedelta, timezone

import pytest

import demand_broker as broker
import demand_closure
import research_work as rw
from test_demand_broker import SLUG
from test_demand_closure import (KEY, MAIN_SHA, MERGE_SHA, NEXT_DAY, NEXT_NOW, PR_URL, QUEUE, RECEIPTS,
                                 RECEIPTS_RAW, SNAP, demand_dir, doc, fnk, gh_for, git_for, own_receipt,
                                 queue_bytes)

DEPLOYED = "28982b47e1c2d3b4a5968778695a4b3c2d1e0f9a"     # the full revision /api/status serves
STATUS_URL = "https://esp-atlas.com/api/status"
SEARCH_URL = "https://esp-atlas.com/api/search?q=fnk0104s"
EXPECTED = ["freenove-fnk0104s"]
RECEIPT_FIELDS = {"http", "deployment", "ids", "query", "checked_at", "merge_sha", "contains_merge"}


def status_body(revision=DEPLOYED, *, deploy=True):
    components = [{"name": "API", "status": "ok", "detail": "serving, index has 900 records"}]
    if deploy:
        component = {"name": "Deploy", "status": "ok", "detail": "commit 28982b4 · main · production"}
        if revision is not ...:
            component["revision"] = revision
        components.append(component)
    return json.dumps({"status": "operational", "generated_at": "2026-11-07T09:00:00+00:00",
                       "components": components}).encode()


def search_body(ids=EXPECTED):
    return json.dumps({"results": [{"id": i, "type": "board", "name": i} for i in ids]}).encode()


class Getter:
    """A fake of demand_closure.default_fetch: url -> (http status, body bytes); records every url.
    `statuses` answers successive /api/status reads (the last one repeats); an answer that is an
    exception instance is raised, as urllib would."""

    def __init__(self, *, statuses=None, search=None):
        self.statuses = list(statuses or [(200, status_body())])
        self.search = search or (200, search_body())
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url == STATUS_URL:
            answer = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        elif url.startswith("https://esp-atlas.com/api/search?"):
            answer = self.search
        else:
            raise AssertionError(f"unexpected live read {url}")
        if isinstance(answer, BaseException):
            raise answer
        return answer


def catalog_search_dir(tmp_path):
    def kind(c):
        c["validation"]["verification_kind"] = rw.KIND_CATALOG_SEARCH
    return demand_dir(tmp_path, queue=queue_bytes(kind))


def live_reserve(d, fetch, **kw):
    return broker.reserve(d, {"date": "2026-11-07", "items": []}, gh=kw.pop("gh", gh_for()),
                          git=kw.pop("git", git_for()), repo_slug=SLUG, today=NEXT_DAY,
                          now=NEXT_NOW, mined_revision=None, new_pam=False, fetch=fetch, **kw)


# --- delivered ----------------------------------------------------------------------------------

def test_exact_ids_at_a_deployment_containing_the_merge_close_delivered(tmp_path):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()
    fetch, git = Getter(), git_for()
    out = live_reserve(d, fetch, git=git)

    assert out.closed == KEY and out.resolution == "delivered" and out.changed is True
    assert fetch.calls == [STATUS_URL, SEARCH_URL, STATUS_URL]        # the search bracketed by one deployment
    assert not [u for u in fetch.calls if "/api/intent" in u]
    assert ("merge-base", "--is-ancestor", MERGE_SHA, DEPLOYED) in git.calls

    c = fnk(d)
    assert c["status"] == "closed" and c["closed_on"] == NEXT_DAY
    ev = c["outcome"]
    assert ev["verification_kind"] == "catalog_search" and ev["query"] == "fnk0104s"
    assert ev["http"] == 200 and ev["deployment"] == DEPLOYED and ev["ids"] == EXPECTED
    assert ev["merge_sha"] == MERGE_SHA and ev["pr_url"] == PR_URL
    assert ev["checked_at"] == NEXT_NOW.isoformat()
    assert c["history"][-1] == {"event": "closed", "date": NEXT_DAY, "resolution": "delivered", "work": KEY,
                                "pr_url": PR_URL, "merge_sha": MERGE_SHA, "deployment": DEPLOYED}
    assert json.loads(before)["candidates"]["fnk0104s"]["history"] == []
    r = own_receipt(d)
    assert r["state"] == "delivered" and r["resolution"]["evidence"] == ev


def test_the_receipt_carries_exactly_the_catalog_search_fields():
    candidate = json.loads(queue_bytes(lambda c: c["validation"].update(verification_kind="catalog_search")))
    candidate = candidate["candidates"]["fnk0104s"]
    pr = {"url": PR_URL, "state": "merged", "merged": True, "merge_sha": MERGE_SHA,
          "merged_at": "2026-11-06T09:19:44Z"}
    receipt, why = demand_closure.observe(candidate, pr, {}, mined_revision=None, git=git_for(),
                                          now=NEXT_NOW, fetch=Getter())
    assert why == ""
    assert set(receipt) == RECEIPT_FIELDS
    assert receipt == {"http": 200, "deployment": DEPLOYED, "ids": EXPECTED, "query": "fnk0104s",
                       "checked_at": NEXT_NOW.isoformat(), "merge_sha": MERGE_SHA, "contains_merge": True}
    assert rw.verify_resolution(candidate, pr, receipt, NEXT_DAY).status == "delivered"


def test_the_checked_at_is_utc_now_even_from_a_local_clock(tmp_path):
    d = catalog_search_dir(tmp_path)
    brasilia = NEXT_NOW.astimezone(timezone(timedelta(hours=-3)))      # 06:00-03:00, the same instant
    out = broker.reserve(d, {"date": NEXT_DAY, "items": []}, gh=gh_for(), git=git_for(),
                         repo_slug=SLUG, today=NEXT_DAY, now=brasilia, new_pam=False, fetch=Getter())
    assert out.resolution == "delivered"
    assert fnk(d)["outcome"]["checked_at"] == "2026-11-07T09:00:00+00:00"


# --- pending: nothing is written -----------------------------------------------------------------

def assert_pending(d, out, queue_before, why):
    assert (d / QUEUE).read_bytes() == queue_before and (d / RECEIPTS).read_bytes() == RECEIPTS_RAW
    assert out.action == rw.RECONCILE and out.key == KEY and not out.changed and not out.closed
    assert why in out.reason


TIMEOUT = socket.timeout("timed out")
SHORT = DEPLOYED[:7]
OTHER = "b" * 40


@pytest.mark.parametrize("fetch, why", [
    (Getter(statuses=[(200, status_body(...))]), "deployed revision"),                  # no revision field
    (Getter(statuses=[(200, status_body(None))]), "deployed revision"),                 # revision null
    (Getter(statuses=[(200, status_body(deploy=False))]), "deployed revision"),         # no Deploy component
    (Getter(statuses=[(200, status_body(SHORT))]), "deployed revision"),                # short sha
    (Getter(statuses=[(200, status_body(DEPLOYED + "0"))]), "deployed revision"),       # 41 chars
    (Getter(statuses=[(200, status_body("--" + DEPLOYED[2:]))]), "deployed revision"),  # option-looking
    (Getter(statuses=[(200, status_body(DEPLOYED)), (200, status_body(OTHER))]), "changed during"),  # mismatched
    (Getter(statuses=[(503, status_body())]), "HTTP 503"),
    (Getter(search=(500, b"")), "HTTP 500"),
    (Getter(search=(404, search_body())), "HTTP 404"),
    (Getter(statuses=[TIMEOUT]), "timed out"),
    (Getter(search=TIMEOUT), "timed out"),
    (Getter(search=TimeoutError("read timed out")), "timed out"),
    (Getter(search=urllib.error.URLError("unreachable")), "unreachable"),
    (Getter(statuses=[(200, b"<html>not json")]), "unreadable"),
    (Getter(search=(200, b"{not json")), "unreadable"),
    (Getter(search=(200, b'{"results": "fnk0104s"}')), "unreadable"),
    (Getter(search=(200, b'{"results": [{"name": "no id"}]}')), "unreadable"),
    (Getter(search=(200, b'[]')), "unreadable"),
    (Getter(statuses=[(200, b'{"components": {"Deploy": 1}}')]), "deployed revision"),
    (Getter(search=(200, search_body([]))), "lacks expected ids"),                         # missing id
    (Getter(search=(200, search_body(EXPECTED + ["freenove-fnk0104s-v2"]))), "undeclared ids"),  # extra id
    (Getter(search=(200, search_body(EXPECTED + ["freenove-fnk0104a"]))), "forbidden sibling"),  # sibling
    (Getter(search=(200, search_body(["freenove-fnk0104a"]))), "lacks expected ids"),
])
def test_an_unproven_live_search_stays_pending(tmp_path, fetch, why):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()
    out = live_reserve(d, fetch)
    assert_pending(d, out, before, why)
    assert not [u for u in fetch.calls if "/api/intent" in u]


@pytest.mark.parametrize("ancestor_rc", [1, 128])           # not an ancestor / unknown revision: never true
def test_a_deployment_without_the_merge_stays_pending(tmp_path, ancestor_rc):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()
    out = live_reserve(d, Getter(), git=git_for(ancestor_rc))
    assert_pending(d, out, before, "merge")


def test_without_an_injected_getter_no_live_search_is_invented(tmp_path):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()
    out = live_reserve(d, None)
    assert_pending(d, out, before, "catalog_search")


def test_an_unmerged_pr_is_never_searched(tmp_path):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()
    fetch = Getter()
    out = live_reserve(d, fetch, gh=gh_for(state="OPEN"))
    assert_pending(d, out, before, "not merged")
    assert fetch.calls == []


def test_a_getter_failure_of_any_kind_stays_pending(tmp_path):
    d = catalog_search_dir(tmp_path)
    before = (d / QUEUE).read_bytes()

    def broken(url):
        raise ValueError("bad url")
    out = live_reserve(d, broken)
    assert_pending(d, out, before, "bad url")


def test_demand_resolution_work_never_reads_the_live_site(tmp_path):
    d = demand_dir(tmp_path)
    fetch = Getter()
    out = broker.reserve(d, SNAP, gh=gh_for(), git=git_for(), repo_slug=SLUG, today=NEXT_DAY, now=NEXT_NOW,
                         mined_revision=MAIN_SHA, new_pam=False, fetch=fetch)
    assert out.closed == KEY and out.resolution == "delivered"
    assert fetch.calls == []
    assert doc(d, QUEUE)["candidates"]["fnk0104s"]["outcome"]["verification_kind"] == "demand_resolution"


# --- the default getter (urllib, short timeout, no new dependency) -------------------------------

class _Response:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_default_fetch_uses_urllib_with_a_short_timeout(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen.update(url=request.full_url, method=request.get_method(), timeout=timeout,
                    headers={k.lower(): v for k, v in request.header_items()})
        return _Response(200, b'{"ok": true}')

    monkeypatch.setattr(demand_closure.urllib.request, "urlopen", urlopen)
    assert demand_closure.default_fetch(SEARCH_URL) == (200, b'{"ok": true}')
    assert seen["url"] == SEARCH_URL and seen["method"] == "GET"
    assert 0 < seen["timeout"] <= 15
    assert seen["headers"].get("cache-control") == "no-cache"


def test_default_fetch_reports_an_http_error_status_instead_of_raising(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(demand_closure.urllib.request, "urlopen", urlopen)
    assert demand_closure.default_fetch(STATUS_URL) == (503, b"")


def test_search_urls_encode_the_term():
    assert demand_closure.search_url("fnk0104s") == SEARCH_URL
    assert demand_closure.search_url("esp32 s3&x=1") == "https://esp-atlas.com/api/search?q=esp32+s3%26x%3D1"
