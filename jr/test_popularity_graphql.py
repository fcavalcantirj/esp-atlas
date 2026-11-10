"""Offline checks for the shared GitHub GraphQL popularity helpers (jr/popularity_graphql.py)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from subprocess import CompletedProcess
from types import SimpleNamespace

import popularity_graphql as gql

NOW = datetime(2026, 11, 7, 19, tzinfo=timezone.utc)


def _ctx(stdout: str, returncode: int = 0, stderr: str = ""):
    return SimpleNamespace(gh=lambda *args: CompletedProcess(args, returncode, stdout, stderr))


def test_query_batches_aliases_with_json_quoted_names():
    query = gql._query(["octo/one", "octo/two"])
    assert 'r0:repository(owner:"octo",name:"one")' in query
    assert 'r1:repository(owner:"octo",name:"two")' in query
    assert query.startswith("query { rateLimit { cost remaining resetAt } ")


def test_cost_bound_is_one_point_per_nonempty_batch():
    assert gql._next_batch_cost_bound(["a/b"]) == 1
    assert gql._next_batch_cost_bound([]) == 0


def test_call_parses_http_head_and_body():
    body = json.dumps({"data": {"rateLimit": {"cost": 1, "remaining": 99}}})
    doc, headers, status = gql._call(_ctx(f"HTTP/2.0 200 OK\nX-Ratelimit-Remaining: 42\n\n{body}"), "q")
    assert status == 200 and headers["x-ratelimit-remaining"] == "42"
    assert doc["data"]["rateLimit"]["remaining"] == 99


def test_call_keeps_partial_data_on_graphql_error_exit():
    body = json.dumps({"data": {"r0": None}, "errors": [{"path": ["r0"]}]})
    doc, _, status = gql._call(_ctx(f"HTTP/2.0 200 OK\n\n{body}", returncode=1), "q")
    assert status == 200 and doc["data"] == {"r0": None}


def test_call_rejects_transport_failures():
    assert gql._call(_ctx("not json"), "q")[0] is None
    assert gql._call(_ctx("[1]"), "q")[0] is None
    assert gql._call(_ctx("{}", returncode=124), "q")[0] is None
    assert gql._call(_ctx("HTTP/2.0 502 Bad\n\n{}", returncode=1), "q")[0] is None
    assert gql._call(_ctx("", returncode=1, stderr="HTTP 403: limit"), "q")[2] == 403


def test_limited_detects_status_and_rate_limited_errors():
    assert gql._limited(None, 429)
    assert gql._limited({"errors": [{"type": "RATE_LIMITED"}]}, 200)
    assert gql._limited({"errors": [{"message": "API rate limit exceeded"}]}, 200)
    assert not gql._limited({"errors": [{"message": "not found"}]}, 200)


def test_quota_takes_the_tighter_remaining_and_header_reset():
    quota = gql._quota({"data": {"rateLimit": {"remaining": 500}}}, {"x-ratelimit-remaining": "30"})
    assert quota["remaining"] == 30
    reset = int((NOW + timedelta(minutes=5)).timestamp())
    assert gql._quota(None, {"x-ratelimit-reset": str(reset)})["resetAt"].startswith("2026-11-07T19:05")
    assert gql._quota(None, {}) is None


def test_cooldown_honours_longer_github_delays_with_one_hour_floor():
    assert gql._cooldown_until(NOW, {}) == NOW + timedelta(hours=1)
    assert gql._cooldown_until(NOW, {"retry-after": "7200"}) == NOW + timedelta(hours=2)
    assert gql._cooldown_until(NOW, {"retry-after": "nonsense"}) == NOW + timedelta(hours=1)
    later = (NOW + timedelta(hours=3)).isoformat()
    assert gql._cooldown_until(NOW, {}, {"resetAt": later}) == NOW + timedelta(hours=3)


def test_charge_cost_counts_known_and_unknown_costs():
    result = SimpleNamespace(graphql_cost_spent=0, graphql_cost_unknown_requests=0)
    gql._charge_cost(result, {"cost": 2})
    gql._charge_cost(result, None)
    assert (result.graphql_cost_spent, result.graphql_cost_unknown_requests) == (2, 1)


def test_repo_id_prefers_consistent_full_database_id():
    assert gql._repo_id({"databaseId": 7, "fullDatabaseId": "7"}) == 7
    assert gql._repo_id({"databaseId": 7, "fullDatabaseId": "8"}) is None
    assert gql._repo_id({"databaseId": 0}) is None


def test_stats_validates_name_identity_and_counts():
    node = {"nameWithOwner": "Octo/One", "databaseId": 5, "stargazerCount": 0, "forkCount": 2}
    assert gql._stats(node, "octo/one", None) == {"id": 5, "stars": 0, "forks": 2}
    assert gql._stats(node, "octo/one", 5) is not None
    assert gql._stats(node, "octo/one", 6) is None
    assert gql._stats(node, "octo/two", None) is None
    assert gql._stats({**node, "stargazerCount": -1}, "octo/one", None) is None
    assert gql._stats(None, "octo/one", None) is None
