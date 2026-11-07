"""Offline adversarial checks for the separate full-catalog GraphQL pass."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import popularity_full as full
from budget import Budget
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)
ALIAS = re.compile(r'r(\d+):repository\(owner:"([^"]+)",name:"([^"]+)"\)')


def _ctx(root, *, remaining=4999, bad_batch=None, bad_status=500, transform=None,
         doc_transform=None, header_remaining=None, max_calls=12, dry_run=False,
         cooldown_until=None, nonzero_calls=()):
    calls = []
    budget = Budget(max_calls=max_calls, max_seconds=150)

    def gh(*args):
        assert args[:4] == ("api", "graphql", "-i", "-f")
        query = args[4].removeprefix("query=")
        calls.append(query)
        if bad_batch is not None and len(calls) == bad_batch:
            return SimpleNamespace(returncode=1, stdout=f"HTTP/2.0 {bad_status} ERROR\n"
                                   "Retry-After: not-a-number\n\n{damaged", stderr=f"HTTP {bad_status}")
        aliases = ALIAS.findall(query)
        data = {"rateLimit": {"cost": 1, "remaining": remaining - len(calls),
                              "resetAt": "2026-11-07T03:00:00Z"}}
        for index, owner, name in aliases:
            node = {"nameWithOwner": f"{owner}/{name}", "databaseId": 1000 + int(name.split("-")[-1])
                    if name.split("-")[-1].isdigit() else 123,
                    "fullDatabaseId": None, "stargazerCount": 40, "forkCount": 5}
            data[f"r{index}"] = transform(owner, name, node) if transform else node
        doc = {"data": data}
        if doc_transform:
            doc = doc_transform(doc, len(calls))
        headers = "X-RateLimit-Resource: graphql\n"
        if header_remaining is not None:
            headers += f"X-RateLimit-Remaining: {header_remaining}\n"
        return SimpleNamespace(returncode=1 if len(calls) in nonzero_calls else 0,
                               stdout="HTTP/2.0 200 OK\n"
                               + headers + "\n" + json.dumps(doc), stderr="")

    ctx = SimpleNamespace(root=root, now=NOW, gh=budget.wrap(gh), budget=budget,
                          dry_run=dry_run, base_sha="test-main", cooldown_until=cooldown_until)
    return ctx, calls


def _receipt(root):
    path = root / full.RECEIPT_DIR / "2026-11-07T02.json"
    return json.loads(path.read_text())


def test_full_pass_attempts_all_146_candidates_in_six_bounded_queries(tmp_path):
    for index in range(146):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}",
                {"stars": 30, "forks": 3, "as_of": "2026-09-20"})
    _record(tmp_path, "nyan", "temporal/nyan-mode", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path)
    result = full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 7  # one quota probe, six <=25-repository batches
    assert all(len(ALIAS.findall(query)) <= 25 for query in calls)
    assert receipt["eligible_repositories"] == receipt["attempted_repositories"] == 146
    assert receipt["validated_repositories"] == 146
    assert receipt["graphql_http_requests"] == 7
    assert receipt["graphql_cost_spent_known"] == 7
    assert receipt["graphql_cost_unknown_requests"] == 0
    assert receipt["outcomes"] == {"excluded_wrong_source": 1, "validated_update": 146}
    assert len(result.paths) == 147  # 146 cited updates plus one per-record receipt
    assert "github_repo_id: 1000" in (tmp_path / "data/firmware/fw-000/firmware.md").read_text()
    assert receipt["records"][0]["age_before_seconds"] is None
    assert receipt["records"][-1]["outcome"] == "excluded_wrong_source"


def test_low_graphql_quota_preserves_every_last_good_and_reports_unattempted(tmp_path):
    path = _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3,
                    "github_repo_id": 1001, "github_as_of": "2026-11-06T02:00:00Z"})
    original = path.read_text()
    ctx, calls = _ctx(tmp_path, remaining=40)
    result = full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 1 and path.read_text() == original
    assert result.paths == ["docs/telemetry/popularity/2026-11-07T02.json"]
    assert receipt["attempted_repositories"] == 0
    assert receipt["records"][0]["outcome"] == "unattempted_rate_limit"
    assert receipt["records"][0]["age_before_seconds"] == 86400


def test_failed_batch_has_no_retry_and_accounts_for_unattempted_tail(tmp_path):
    for index in range(60):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, bad_batch=3)
    full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 3  # probe, first batch, failed second batch
    assert receipt["attempted_repositories"] == 50
    assert receipt["outcomes"] == {"attempted_query_failure": 25,
                                   "unattempted_query_failure": 10, "validated_update": 25}


@pytest.mark.parametrize("status", [403, 429])
def test_damaged_rate_response_sets_cooldown_and_next_run_skips_every_repo(tmp_path, status):
    for index in range(30):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, bad_batch=2, bad_status=status)
    first = full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2 and receipt["attempted_repositories"] == 25
    assert receipt["outcomes"] == {"attempted_rate_limited": 25,
                                   "unattempted_rate_limit": 5}
    until = first.items[0]["cooldown_until"]
    assert until >= "2026-11-07T03:00:00"
    ctx2, calls2 = _ctx(tmp_path, cooldown_until=until)
    ctx2.now = NOW.replace(minute=30)
    full.run(ctx2)
    assert calls2 == []
    assert _receipt(tmp_path)["outcomes"] == {"unattempted_cooldown": 30}


def test_duplicate_catalog_records_share_one_repository_lookup(tmp_path):
    a = _record(tmp_path, "first", "owner/repo-001", {"stars": 30, "forks": 3})
    b = _record(tmp_path, "second", "owner/repo-001", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path)
    full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2 and len(ALIAS.findall(calls[1])) == 1
    assert receipt["eligible_repositories"] == receipt["attempted_repositories"] == 1
    assert receipt["outcomes"] == {"validated_update": 2}
    assert "github_repo_id: 1001" in a.read_text() and "github_repo_id: 1001" in b.read_text()


def test_http_200_partial_rate_error_keeps_valid_siblings_and_stops(tmp_path):
    for index in range(30):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}", {"stars": 30, "forks": 3})

    def partial(doc, call_number):
        if call_number == 2:
            doc["data"]["r4"] = None
            doc["errors"] = [{"type": "RATE_LIMITED", "message": "rate limit exceeded",
                              "path": ["r4"]}]
        return doc

    ctx, calls = _ctx(tmp_path, doc_transform=partial, nonzero_calls=(2,))
    result = full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2
    assert receipt["outcomes"] == {"attempted_graphql_error": 1,
                                   "unattempted_rate_limit": 5, "validated_update": 24}
    assert result.items[0]["cooldown_until"] >= "2026-11-07T03:00:00"


def test_http_header_quota_can_stop_even_when_body_reports_more(tmp_path):
    _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, header_remaining=40)
    full.run(ctx)
    assert len(calls) == 1
    assert _receipt(tmp_path)["outcomes"] == {"unattempted_rate_limit": 1}


def test_http_200_rate_error_envelope_with_no_data_stops_first_batch(tmp_path):
    for index in range(30):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}", {"stars": 30, "forks": 3})

    def error_envelope(doc, call_number):
        return {"errors": [{"type": "RATE_LIMITED", "message": "rate limit exceeded"}]} if call_number == 2 else doc

    ctx, calls = _ctx(tmp_path, doc_transform=error_envelope, nonzero_calls=(2,))
    result = full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2 and receipt["attempted_repositories"] == 25
    assert receipt["outcomes"] == {"attempted_rate_limited": 25, "unattempted_rate_limit": 5}
    assert result.items[0]["cooldown_until"] >= "2026-11-07T03:00:00"


def test_valid_retry_after_http_date_extends_cooldown():
    until = full._cooldown_until(NOW, {"retry-after": "Sat, 07 Nov 2026 05:00:00 GMT"})
    assert until.isoformat() == "2026-11-07T05:00:00+00:00"


def test_identity_drift_negative_counts_and_floor_preserve_last_good(tmp_path):
    a = _record(tmp_path, "bad-id", "owner/repo-001", {"stars": 30, "forks": 3,
                "github_repo_id": 999, "github_as_of": "2026-11-06T02:00:00Z"})
    b = _record(tmp_path, "bad-count", "owner/repo-002", {"stars": 30, "forks": 3})
    c = _record(tmp_path, "below-floor", "owner/repo-003", {"stars": 30, "forks": 3})
    before = {p: p.read_text() for p in (a, b, c)}

    def transform(owner, name, node):
        if name == "repo-002":
            node["stargazerCount"] = -1
        if name == "repo-003":
            node["stargazerCount"], node["forkCount"] = 1, 0
        return node

    ctx, calls = _ctx(tmp_path, transform=transform)
    full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2 and all(path.read_text() == text for path, text in before.items())
    assert receipt["outcomes"] == {"attempted_below_floor": 1,
                                   "attempted_invalid_identity_or_counts": 2}
    assert receipt["attempted_repositories"] == 3


def test_budget_exhaustion_marks_remaining_repos_without_a_call(tmp_path):
    for index in range(60):
        _record(tmp_path, f"fw-{index:03}", f"owner/repo-{index:03}", {"stars": 30, "forks": 3})
    ctx, calls = _ctx(tmp_path, max_calls=2)
    full.run(ctx)
    receipt = _receipt(tmp_path)
    assert len(calls) == 2 and receipt["attempted_repositories"] == 25
    assert receipt["outcomes"] == {"unattempted_budget": 35, "validated_update": 25}


def test_dry_run_changes_no_records_and_declares_receipt(tmp_path):
    path = _record(tmp_path, "fw", "owner/repo-001", {"stars": 30, "forks": 3})
    before = path.read_text()
    ctx, _ = _ctx(tmp_path, dry_run=True)
    result = full.run(ctx)
    assert path.read_text() == before
    assert not (tmp_path / full.RECEIPT_DIR).exists()
    assert len(result.would_write) == 2
