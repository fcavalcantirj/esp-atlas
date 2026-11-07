"""Primary Postgres coordinator tests; set TEST_POPULARITY_DATABASE_URL to run locally.

The database must have migrations/20261106_live_popularity.sql applied. This suite uses
only that disposable database and never calls GitHub.
"""
import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import esp_atlas_api.live_popularity as popularity_module
from esp_atlas_api.live_popularity import PostgresPopularityStore, identity_from_record
from test_live_popularity import RECORD


@pytest.fixture
def pg_store():
    dsn = os.environ.get("TEST_POPULARITY_DATABASE_URL")
    if not dsn:
        pytest.skip("set TEST_POPULARITY_DATABASE_URL for the local Postgres coordinator tests")
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM popularity_refresh_repo")
        conn.execute("UPDATE popularity_refresh_budget SET hour_start=date_trunc('hour', clock_timestamp()), used=0, lease_token=NULL, lease_until=NULL, cooldown_until=NULL WHERE singleton=true")
    return PostgresPopularityStore(dsn)


def _row(dsn, table, where=""):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        return conn.execute(f"SELECT * FROM {table} {where}").fetchone()


def _wait_until_budget_lock_is_contended(dsn):
    """Prove the worker reached FOR UPDATE before releasing the holder."""
    import psycopg
    deadline = time.monotonic() + 1.2
    with psycopg.connect(dsn, autocommit=True) as conn:
        while time.monotonic() < deadline:
            waiting = conn.execute("""SELECT count(*) FROM pg_stat_activity
                WHERE pid <> pg_backend_pid() AND wait_event_type='Lock'
                  AND query LIKE 'SELECT * FROM popularity_refresh_budget%'""").fetchone()[0]
            if waiting:
                return
            time.sleep(0.01)
    raise AssertionError("publisher/claimant never contended on the budget row")


def test_two_instances_compete_for_one_committed_global_and_repo_lease(pg_store):
    identity = identity_from_record(RECORD)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda token: pg_store.claim(identity, token), ["first", "second"]))
    assert sorted(r.action for r in results) == ["fetch", "wait"]
    budget = _row(pg_store.dsn, "popularity_refresh_budget")
    assert budget["used"] == 1 and budget["lease_token"] in ("first", "second")
    other = replace(identity, repo_id=987)
    assert pg_store.claim(other, "third").action == "wait"  # one global in-flight lease


def test_fenced_publish_rejects_expired_old_worker_after_a_new_claim(pg_store):
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "old").action == "fetch"
    import psycopg
    with psycopg.connect(pg_store.dsn, autocommit=True) as conn:
        conn.execute("UPDATE popularity_refresh_budget SET lease_until=clock_timestamp()-interval '1 second'")
        conn.execute("UPDATE popularity_refresh_repo SET lease_until=clock_timestamp()-interval '1 second'")
    assert pg_store.claim(identity, "new").action == "fetch"
    assert pg_store.publish(identity, "old", 999, 999) is None
    assert pg_store.publish(identity, "new", 0, 0).stars == 0
    repo = _row(pg_store.dsn, "popularity_refresh_repo")
    assert repo["stars"] == 0 and repo["forks"] == 0 and repo["lease_token"] is None


def test_global_budget_caps_at_twenty_and_resets_at_the_utc_hour(pg_store):
    identity = identity_from_record(RECORD)
    for n in range(20):
        token = f"token-{n}"
        assert pg_store.claim(identity, token).action == "fetch"
        pg_store.fail(identity, token)
    assert pg_store.claim(identity, "over-budget").action == "budget"
    assert _row(pg_store.dsn, "popularity_refresh_budget")["used"] == 20
    import psycopg
    with psycopg.connect(pg_store.dsn, autocommit=True) as conn:
        conn.execute("UPDATE popularity_refresh_budget SET hour_start=hour_start-interval '1 hour'")
    assert pg_store.claim(identity, "new-hour").action == "fetch"
    assert _row(pg_store.dsn, "popularity_refresh_budget")["used"] == 1


def test_cooldown_blocks_claim_across_instances_and_does_not_erase_last_good(pg_store):
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "first").action == "fetch"
    pg_store.publish(identity, "first", 0, 0)
    import psycopg
    with psycopg.connect(pg_store.dsn, autocommit=True) as conn:
        conn.execute("UPDATE popularity_refresh_repo SET observed_at=clock_timestamp()-interval '2 hours'")
    assert pg_store.claim(identity, "second").action == "fetch"
    pg_store.fail(identity, "second", global_cooldown=60, repo_backoff=60)
    blocked = pg_store.claim(identity, "third")
    assert blocked.action == "wait" and blocked.snapshot.stars == 0
    assert blocked.retry_after_seconds >= 1


def test_catalog_newer_than_cache_forces_a_claim_without_reusing_old_counts(pg_store):
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "first").action == "fetch"
    published = pg_store.publish(identity, "first", 9, 3)
    catalog_ahead = replace(identity, github_as_of=published.observed_at)
    claim = pg_store.claim(catalog_ahead, "second")
    assert claim.action == "fetch" and claim.snapshot.stars == 9


def test_newly_cited_name_for_same_repo_id_invalidates_old_name_cache(pg_store):
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "old").action == "fetch"
    assert pg_store.publish(identity, "old", 9, 3) is not None
    renamed = replace(identity, full_name="example/renamed",
                      source_url="https://github.com/example/renamed")
    claim = pg_store.claim(renamed, "new")
    assert claim.action == "fetch" and claim.snapshot is None
    repo = _row(pg_store.dsn, "popularity_refresh_repo")
    assert repo["full_name"] == "example/renamed" and repo["stars"] is None
    assert pg_store.publish(identity, "new", 100, 100) is None
    assert pg_store.publish(renamed, "new", 0, 0) is not None


def test_publish_rechecks_expiry_after_waiting_for_the_budget_lock(pg_store):
    import psycopg
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "late").action == "fetch"
    with psycopg.connect(pg_store.dsn, autocommit=True) as conn:
        conn.execute("UPDATE popularity_refresh_budget SET lease_until=clock_timestamp()+interval '650 milliseconds'")
        conn.execute("UPDATE popularity_refresh_repo SET lease_until=clock_timestamp()+interval '650 milliseconds'")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(pg_store.dsn, autocommit=True) as holder:
            with holder.transaction():
                holder.execute("SELECT * FROM popularity_refresh_budget WHERE singleton=true FOR UPDATE")
                future = pool.submit(pg_store.publish, identity, "late", 99, 8)
                _wait_until_budget_lock_is_contended(pg_store.dsn)
                time.sleep(0.75)  # expires while blocked, below statement_timeout
            assert future.result(timeout=2) is None
    repo = _row(pg_store.dsn, "popularity_refresh_repo")
    assert repo["stars"] is None and repo["forks"] is None


def test_claim_uses_post_lock_utc_hour_when_wait_crosses_boundary(pg_store, monkeypatch):
    import psycopg
    identity = identity_from_record(RECORD)
    before = datetime(2026, 11, 7, 0, 59, 59, tzinfo=timezone.utc)
    after = before + timedelta(seconds=2)
    released = threading.Event()
    monkeypatch.setattr(popularity_module, "_db_now", lambda conn: after if released.is_set() else before)
    with psycopg.connect(pg_store.dsn, autocommit=True) as conn:
        conn.execute("UPDATE popularity_refresh_budget SET hour_start=%s, used=20",
                     (before.replace(minute=0, second=0),))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(pg_store.dsn, autocommit=True) as holder:
            with holder.transaction():
                holder.execute("SELECT * FROM popularity_refresh_budget WHERE singleton=true FOR UPDATE")
                future = pool.submit(pg_store.claim, identity, "next-hour")
                _wait_until_budget_lock_is_contended(pg_store.dsn)
                released.set()
            assert future.result(timeout=2).action == "fetch"
    budget = _row(pg_store.dsn, "popularity_refresh_budget")
    assert budget["hour_start"] == after.replace(minute=0, second=0)
    assert budget["used"] == 1


def test_failure_cooldown_starts_after_lock_wait(pg_store, monkeypatch):
    import psycopg
    identity = identity_from_record(RECORD)
    assert pg_store.claim(identity, "rate-limited").action == "fetch"
    before = datetime(2026, 11, 7, 1, 0, 0, tzinfo=timezone.utc)
    after = before + timedelta(minutes=2)
    released = threading.Event()
    monkeypatch.setattr(popularity_module, "_db_now", lambda conn: after if released.is_set() else before)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(pg_store.dsn, autocommit=True) as holder:
            with holder.transaction():
                holder.execute("SELECT * FROM popularity_refresh_budget WHERE singleton=true FOR UPDATE")
                future = pool.submit(pg_store.fail, identity, "rate-limited", global_cooldown=60)
                _wait_until_budget_lock_is_contended(pg_store.dsn)
                released.set()
            future.result(timeout=2)
    assert _row(pg_store.dsn, "popularity_refresh_budget")["cooldown_until"] == after + timedelta(seconds=60)


@pytest.mark.parametrize("fault", ["body_timeout", "body_read_error", "oversized_body"])
def test_rate_limit_headers_survive_bad_body_and_block_other_repo(pg_store, monkeypatch, fault):
    """A 429 is acted on from headers, even when its body cannot be consumed."""
    seen = {"body_reads": 0, "http_calls": 0}

    class Response:
        status_code = 429
        headers = {"Retry-After": "120"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            if fault == "body_timeout":
                raise TimeoutError("response body timed out")
            if fault == "body_read_error":
                raise popularity_module.httpx.ReadError("response body failed")

        async def aiter_bytes(self):
            seen["body_reads"] += 1
            yield b"x" * 65537  # would exceed the normal body cap if consumed

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        def stream(self, *args, **kwargs):
            seen["http_calls"] += 1
            return Response()

    monkeypatch.setattr(popularity_module.httpx, "AsyncClient", Client)
    response = asyncio.run(popularity_module.live_popularity(RECORD, store=pg_store))
    assert response["outcome"] == "unavailable" and response["retry_after_seconds"] == 120
    assert seen == {"body_reads": 0, "http_calls": 1}
    identity = identity_from_record(RECORD)
    other = replace(identity, repo_id=987, full_name="other/repo")
    blocked = pg_store.claim(other, "other-repo")
    assert blocked.action == "wait" and blocked.retry_after_seconds > 0
    assert _row(pg_store.dsn, "popularity_refresh_budget")["used"] == 1
