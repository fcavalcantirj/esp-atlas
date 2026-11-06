"""PAM discovery contract: toy fixtures only; no third-party spec mirroring."""
from copy import deepcopy
import datetime as dt
import json

import pytest

import pam_leads as pam


NOW = dt.datetime(2026, 11, 6, 1, 0, tzinfo=dt.timezone.utc)


def feeds():
    products = {"count": 3, "products": [
        {"id": "vendor-es3c28p", "name": "ES3C28P", "chip": "ESP32-S3",
         "page": "https://pamfinds.com/esp32/vendor-es3c28p/",
         "buy": "https://pamfinds.com/go/affiliate/", "specs_summary": {"flash_mb": "COPY-ME-NOT"}},
        {"id": "vendor-es3n28p", "name": "ES3N28P", "chip": "ESP32-S3",
         "page": "https://pamfinds.com/esp32/vendor-es3n28p/"},
        {"id": "other-chip", "name": "Other board", "chip": "RP2040"},
    ]}
    specs = {"count": 3, "products": [
        {"id": "vendor-es3n28p", "specs": {"flash_mb": {"value": "COPY-ME-NOT",
          "source": "https://manufacturer.example/es3n28p"}}},
        {"id": "other-chip", "specs": {}},
        {"id": "vendor-es3c28p", "specs": {"flash_mb": {"value": "COPY-ME-NOT",
          "source": "https://manufacturer.example/es3c28p"}}},
    ]}
    return {"products": products, "specs": specs}


def reply(name, data, status=200):
    return pam.FeedReply(status=status, payload=data if status == 200 else None,
                         etag=f'"{name}-etag"', sha256="a" * 64, size=100)


class Fetch:
    def __init__(self, data=None, statuses=None):
        self.data = data or feeds()
        self.statuses = statuses or {}
        self.calls = []

    def __call__(self, name, etag=None):
        self.calls.append((name, etag))
        statuses = self.statuses.get(name, [200])
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        if status == 503:
            raise pam.FeedError("unavailable")
        return reply(name, self.data[name], status)


def state(catalog=()):
    return pam.refresh(None, list(catalog), now=NOW, fetch=Fetch())


def test_explicit_id_join_scope_and_minimal_provenance():
    result = state()
    assert len(result["leads"]) == 2
    lead = next(x for x in result["leads"] if x["source_id"] == "vendor-es3c28p")
    assert lead["source_pointers"] == {"flash_mb": ["https://manufacturer.example/es3c28p"]}
    assert result["feeds"]["products"]["url"] == pam.ENDPOINTS["products"]
    assert result["feeds"]["products"]["sha256"] == "a" * 64
    assert result["source"] == "pam_feed"
    serialized = json.dumps(result)
    assert "COPY-ME-NOT" not in serialized and "affiliate" not in serialized
    assert "searches" not in result and "window" not in result


def test_exact_label_alias_match_never_conflates_sibling_or_chip():
    result = state([{"id": "catalog-c", "name": "Example", "aka": ["ES3C28P"], "soc": "esp32-s3"}])
    c, n = result["leads"]
    assert c["matches"] == ["catalog-c"] and c["status"] == "possible_match"
    assert n["matches"] == [] and n["status"] == "potential_identity_gap"
    candidates = pam.candidate_leads(result)
    assert [x["source_id"] for x in candidates] == ["vendor-es3n28p"]
    assert candidates[0]["identity_verified"] is False


def test_ambiguous_exact_alias_is_not_silently_chosen():
    result = state([{"id": "a", "aka": ["ES3C28P"]}, {"id": "b", "aka": ["ES3C28P"]}])
    assert result["leads"][0]["status"] == "ambiguous_match"
    assert result["leads"][0]["matches"] == ["a", "b"]


def test_304_reuses_minimal_state_but_rechecks_current_catalog():
    before = state()
    original = deepcopy(before)
    fetch = Fetch(statuses={"products": [304], "specs": [304]})
    result = pam.refresh(before, [{"id": "catalog-c", "name": "ES3C28P"}], now=NOW, fetch=fetch)
    assert before == original
    assert result["leads"][0]["matches"] == ["catalog-c"]
    assert fetch.calls == [("products", '"products-etag"'), ("specs", '"specs-etag"')]
    assert result["feeds"] == before["feeds"]


def test_partial_304_refetches_the_other_feed_before_joining():
    fetch = Fetch(statuses={"products": [304, 200], "specs": [200]})
    pam.refresh(state(), [], now=NOW, fetch=fetch)
    assert fetch.calls[-1] == ("products", None)


@pytest.mark.parametrize("mutation", [
    lambda d: d["specs"]["products"].pop(),
    lambda d: d["products"]["products"].append(d["products"]["products"][0]),
    lambda d: d["products"].update(count=99),
    lambda d: d["specs"]["products"][0].update(id="unknown-board"),
    lambda d: d["products"]["products"][0].update(id="../../injected"),
    lambda d: d["specs"]["products"][0].update(specs="not-a-map"),
])
def test_malformed_or_inconsistent_feeds_preserve_old_state(mutation):
    previous = state()
    original = deepcopy(previous)
    data = feeds()
    mutation(data)
    with pytest.raises(pam.FeedError):
        pam.refresh(previous, [], now=NOW, fetch=Fetch(data))
    assert previous == original


def test_failed_feed_does_not_return_partial_replacement_state():
    previous = state()
    original = deepcopy(previous)
    with pytest.raises(pam.FeedError):
        pam.refresh(previous, [], now=NOW, fetch=Fetch(statuses={"specs": [503]}))
    assert previous == original


def test_unexpected_304_and_corrupt_cache_fail_closed():
    with pytest.raises(pam.FeedError):
        pam.refresh(None, [], now=NOW, fetch=Fetch(statuses={"products": [304], "specs": [304]}))
    with pytest.raises(pam.FeedError):
        pam.refresh({"version": 99}, [], now=NOW, fetch=Fetch())


@pytest.mark.parametrize("mutate", [
    lambda s: s["leads"][0].update(specs={"flash_mb": "COPY-ME-NOT"}),
    lambda s: s["leads"][0].update(name_hint="Changed without a matching fingerprint"),
    lambda s: s["feeds"]["products"].update(fetched_at="yesterday"),
    lambda s: s["feeds"]["products"].update(sha256="not-a-hash"),
    lambda s: s["leads"][0].pop("status"),
    lambda s: s.pop("checked_at"),
])
def test_corrupt_cached_metadata_is_not_republished_on_304(mutate):
    previous = state()
    mutate(previous)
    with pytest.raises(pam.FeedError):
        pam.refresh(previous, [], now=NOW, fetch=Fetch(statuses={"products": [304], "specs": [304]}))


def test_semantic_work_key_is_not_the_daily_date_etag_or_feed_hash():
    a = state()
    b = deepcopy(a)
    b["checked_at"] = "2026-11-07T01:00:00Z"
    b["feeds"]["products"].update(etag='"changed"', sha256="b" * 64)
    assert [x["key"] for x in pam.candidate_leads(a)] == [x["key"] for x in pam.candidate_leads(b)]
    handled = {x["key"] for x in pam.candidate_leads(a)}
    assert pam.candidate_leads(b, handled_keys=handled) == []


def test_source_pointer_change_is_research_only_and_retains_fetch_provenance():
    a = state()
    data = feeds()
    data["specs"]["products"][2]["specs"]["flash_mb"]["source"] += "/revision-b"
    b = pam.refresh(None, [], now=NOW, fetch=Fetch(data))
    assert pam.candidate_leads(a)[0]["key"] != pam.candidate_leads(b)[0]["key"]
    lead = pam.candidate_leads(b)[0]
    assert lead["phase"] == "research" and lead["provenance"]["feeds"] == b["feeds"]
    assert "window" not in lead and "metrics" not in lead


def test_dangerous_pointers_are_not_exported_or_followed():
    data = feeds()
    data["specs"]["products"][2]["specs"] = {
        "local": {"value": "x", "source": "http://127.0.0.1/admin"},
        "local_https": {"value": "x", "source": "https://127.0.0.1/admin"},
        "ipv6": {"value": "x", "source": "https://[::1]/admin"},
        "userinfo": {"value": "x", "source": "https://user:pass@example.com/path"},
        "file": {"value": "x", "source": "file:///etc/passwd"},
        "malformed": {"value": "x", "source": "https://["},
    }
    result = pam.refresh(None, [], now=NOW, fetch=Fetch(data))
    assert result["leads"][0]["source_pointers"] == {}


def test_fetch_is_fixed_endpoint_and_bounded(monkeypatch):
    with pytest.raises(pam.FeedError):
        pam.fetch_feed("https://attacker.example/feed")
    class Response:
        status = 200
        headers = {"Content-Type": "application/json", "ETag": '"v1"'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, limit):
            assert limit == pam.MAX_BYTES + 1
            return b"x" * limit
    seen = []
    def open_url(req, timeout):
        seen.append((req.full_url, timeout))
        return Response()
    monkeypatch.setattr(pam._OPENER, "open", open_url)
    with pytest.raises(pam.FeedError, match="size"):
        pam.fetch_feed("products")
    assert seen == [(pam.ENDPOINTS["products"], pam.TIMEOUT_SECONDS)]
