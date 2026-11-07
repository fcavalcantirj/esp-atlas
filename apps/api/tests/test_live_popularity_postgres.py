"""Primary Postgres coordinator tests; set TEST_POPULARITY_DATABASE_URL to run locally.

The database must have migrations/20261106_live_popularity.sql applied. This suite uses
only that disposable database and never calls GitHub.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

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
