"""Offline contract checks for the optional on-view GitHub count overlay."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

import esp_atlas_api.main as main_module
import esp_atlas_api.live_popularity as popularity_module
from esp_atlas_api.live_popularity import Claim, Snapshot, identity_from_record, live_popularity


URL = "https://github.com/example/firmware"
RECORD = {
    "id": "example", "url": URL,
    "popularity": {"stars": 10, "forks": 2, "github_repo_id": 123,
                   "github_as_of": "2025-01-01T00:00:00Z"},
    "sources": [
        {"field": "popularity.github_repo_id", "url": URL},
        {"field": "popularity.github_as_of", "url": URL},
    ],
}
NEW = Snapshot(0, 0, datetime(2026, 11, 7, tzinfo=timezone.utc), "example/firmware", 123)


class Store:
    def __init__(self, claim=None, published=NEW):
        self.result = claim or Claim("fetch")
        self.published = published
        self.claims = []
        self.publishes = []
        self.failures = []

    def claim(self, identity, token):
        self.claims.append((identity, token))
        return self.result

    def publish(self, identity, token, stars, forks):
        self.publishes.append((identity, token, stars, forks))
        return self.published

    def fail(self, identity, token, **kw):
        self.failures.append((identity, token, kw))


def run(store, fetch, record=RECORD):
    return asyncio.run(live_popularity(record, store=store, fetch=fetch))


def result(status=200, **values):
    body = {"id": 123, "full_name": "example/firmware",
            "stargazers_count": 0, "forks_count": 0, **values}
    return status, json.dumps(body).encode(), {}


def test_only_a_bare_cited_github_url_and_positive_repo_id_are_eligible():
    assert identity_from_record(RECORD).repo_id == 123
    for changed in (
        {"url": "https://github.com/example/firmware/issues"},
        {"url": "https://github.com/example/firmware/"},
        {"url": "https://evil.example/example/firmware"},
        {"popularity": {**RECORD["popularity"], "github_repo_id": 0}},
        {"popularity": {**RECORD["popularity"], "github_repo_id": True}},
        {"sources": RECORD["sources"][:1]},
    ):
        assert identity_from_record({**RECORD, **changed}) is None


def test_ineligible_record_never_claims_or_fetches():
    store = Store()
    async def fetch(_):
        raise AssertionError("GitHub must not be called")
    response = run(store, fetch, {**RECORD, "popularity": {"stars": 10, "forks": 2}})
    assert response["outcome"] == "ineligible" and response["github"] is None
    assert store.claims == []


def test_no_store_means_no_github_request(monkeypatch):
    monkeypatch.delenv("POPULARITY_DATABASE_URL", raising=False)
    async def fetch(_):
        raise AssertionError("GitHub must not be called")
    response = asyncio.run(live_popularity(RECORD, fetch=fetch))
    assert response["outcome"] == "unavailable" and response["github"] is None


def test_ambiguous_claim_failure_never_starts_github():
    class FailedStore(Store):
        def claim(self, identity, token):
            raise ConnectionError("commit acknowledgement lost")
    async def fetch(_):
        raise AssertionError("GitHub must not be called after an ambiguous claim")
    response = run(FailedStore(), fetch)
    assert response["outcome"] == "unavailable" and response["github"] is None


def test_valid_zero_counts_publish_as_fresh_with_source_and_date():
    store = Store()
    async def fetch(_):
        return result()
    response = run(store, fetch)
    assert response["outcome"] == "fresh"
    assert response["github"] == {"stars": 0, "forks": 0, "observed_at": "2026-11-07T00:00:00Z",
                                  "source_url": URL, "repo_id": 123}
    assert response["catalog"]["stars"] == 10 and response["catalog"]["github_as_of"] == "2025-01-01T00:00:00Z"
    assert store.publishes[0][2:] == (0, 0)


@pytest.mark.parametrize("body", [
    {"id": 124}, {"full_name": "other/firmware"}, {"stargazers_count": None},
    {"forks_count": -1}, {"forks_count": False},
])
def test_wrong_identity_or_incomplete_counts_keep_last_good(body):
    store = Store(Claim("fetch", NEW))
    async def fetch(_):
        return result(**body)
    response = run(store, fetch)
    assert response["outcome"] == "stale" and response["github"]["stars"] == 0
    assert store.publishes == [] and store.failures[0][2]["repo_backoff"] == 60


def test_cached_snapshot_does_not_fetch_or_publish():
    store = Store(Claim("cached", NEW))
    async def fetch(_):
        raise AssertionError("cached result must not fetch")
    response = run(store, fetch)
    assert response["outcome"] == "cached" and response["github"]["repo_id"] == 123
    assert store.publishes == []


def test_failed_publish_never_claims_fresh():
    store = Store(Claim("fetch", NEW), published=None)
    async def fetch(_):
        return result(stargazers_count=200)
    response = run(store, fetch)
    assert response["outcome"] == "stale" and response["github"]["stars"] == 0


def test_catalog_newer_than_cached_overlay_is_not_replaced():
    record = {**RECORD, "popularity": {**RECORD["popularity"], "github_as_of": "2026-11-08T00:00:00Z"}}
    store = Store(Claim("cached", NEW))
    async def fetch(_):
        raise AssertionError("cached response must not fetch")
    response = run(store, fetch, record)
    assert response["outcome"] == "unavailable" and response["github"] is None


def test_budget_wait_returns_last_good_and_retry_delay_without_fetch():
    store = Store(Claim("budget", NEW, retry_after_seconds=1700))
    async def fetch(_):
        raise AssertionError("budget wait must not fetch")
    response = run(store, fetch)
    assert response["outcome"] == "stale" and response["retry_after_seconds"] == 1700


def test_headerless_429_starts_global_cooldown_and_keeps_catalog():
    store = Store()
    async def fetch(_):
        return 429, b"{}", {}
    response = run(store, fetch)
    assert response["outcome"] == "unavailable" and response["github"] is None
    assert response["retry_after_seconds"] == 60
    assert store.failures[0][2]["global_cooldown"] == 60


def test_403_retry_after_header_controls_global_cooldown():
    store = Store()
    async def fetch(_):
        return 403, b"{}", {"retry-after": "120"}
    response = run(store, fetch)
    assert response["retry_after_seconds"] == 120
    assert store.failures[0][2]["global_cooldown"] == 120


@pytest.mark.parametrize("phase", ["connect", "body"])
def test_github_deadline_covers_connection_and_complete_body(monkeypatch, phase):
    class Response:
        status_code = 200
        headers = {}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def aiter_bytes(self):
            yield b"{"
            if phase == "body":
                await asyncio.sleep(0.1)
            yield b"}"

    class Client:
        def __init__(self, **kw):
            assert kw["follow_redirects"] is False
        async def __aenter__(self):
            if phase == "connect":
                await asyncio.sleep(0.1)
            return self
        async def __aexit__(self, *args):
            pass
        def stream(self, *args, **kw):
            return Response()

    monkeypatch.setattr(popularity_module, "_FETCH_DEADLINE", 0.02)
    monkeypatch.setattr(popularity_module.httpx, "AsyncClient", Client)
    with pytest.raises(TimeoutError):
        asyncio.run(popularity_module.fetch_github(identity_from_record(RECORD)))


def test_route_loads_canonical_record_and_is_not_cached(client, monkeypatch):
    seen = []
    async def fake(record):
        seen.append(record)
        return {"firmware_id": record["id"], "outcome": "ineligible",
                "catalog": {"stars": None, "forks": None, "github_as_of": None,
                            "source_url": record["url"], "repo_id": None},
                "github": None, "retry_after_seconds": None}
    monkeypatch.setattr(main_module, "live_popularity", fake)
    response = client.get("/firmware/nucleoos/popularity/live")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["firmware_id"] == "nucleoos"
    assert seen[0]["url"] == "https://github.com/indecenti/NucleoOs"
    missing = client.get("/firmware/no-such-id/popularity/live")
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"


def test_cited_catalog_is_served_without_configured_coordinator(client, monkeypatch):
    monkeypatch.delenv("POPULARITY_DATABASE_URL", raising=False)
    response = client.get("/firmware/nucleoos/popularity/live")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["outcome"] == "unavailable" and body["github"] is None
    assert body["catalog"] == {"stars": 100, "forks": 7, "github_as_of": "2026-11-06T21:00:55Z",
                               "source_url": "https://github.com/indecenti/NucleoOs", "repo_id": 1268267248}
