"""Offline checks for the bounded catalog popularity stage."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
import jsonschema

import pending_prs
import stage_popularity_refresh as refresh
from budget import Budget

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)


def _record(root: Path, fid: str, repo: str, pop: dict) -> Path:
    path = root / "data" / "firmware" / fid / "firmware.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {"id": fid, "type": "firmware", "name": fid,
             "url": f"https://github.com/{repo}", "category": "multi",
             "socs": ["esp32-s3"], "popularity": pop,
             "sources": [{"field": "popularity", "url": f"https://github.com/{repo}",
                          "verified": "2026-09-20"}]}
    path.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\nBody.\n")
    return path


def _ctx(root: Path, response: dict, dry_run=False):
    calls = []

    def gh(*args):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")

    return SimpleNamespace(root=root, now=NOW, gh=gh, budget=Budget(), dry_run=dry_run), calls


def _fm(path: Path):
    return yaml.safe_load(path.read_text().split("---", 2)[1])


def test_refresh_preserves_non_github_signals_and_their_dates(tmp_path):
    path = _record(tmp_path, "example", "owner/example",
                   {"stars": 10, "forks": 2, "downloads": 2040,
                    "editorial_home": "https://example.org", "as_of": "2026-09-20"})
    ctx, calls = _ctx(tmp_path, {"full_name": "owner/example", "id": 123,
                                "stargazers_count": 11, "forks_count": 3})
    result = refresh.run(ctx)
    pop = _fm(path)["popularity"]
    assert calls == [("api", "repos/owner/example")]
    assert result.paths == ["data/firmware/example/firmware.md"]
    assert pop["stars"] == 11 and pop["forks"] == 3 and pop["github_repo_id"] == 123
    assert pop["github_as_of"] == "2026-11-06T00:00:00Z"
    assert pop["downloads"] == 2040 and "downloads_as_of" not in pop
    assert "editorial_home_as_of" not in pop and pop["as_of"] == "2026-09-20"
    fields = {s["field"] for s in _fm(path)["sources"]}
    assert {"popularity.stars", "popularity.forks", "popularity.github_as_of"} <= fields
    schema = json.loads((Path(__file__).resolve().parents[1] / "schema" / "firmware.schema.json").read_text())
    jsonschema.validate(pop, schema["properties"]["popularity"], format_checker=jsonschema.FormatChecker())


def test_identity_drift_or_incomplete_payload_preserves_last_good(tmp_path):
    path = _record(tmp_path, "example", "owner/example",
                   {"stars": 10, "forks": 2, "github_repo_id": 123, "as_of": "2026-09-20"})
    original = path.read_text()
    for bad in ({"full_name": "owner/example", "id": 999, "stargazers_count": 11, "forks_count": 3},
                {"full_name": "new-owner/example", "id": 123, "stargazers_count": 11, "forks_count": 3},
                {"full_name": "owner/example", "id": 123, "stargazers_count": 11, "forks_count": None}):
        ctx, _ = _ctx(tmp_path, bad)
        result = refresh.run(ctx)
        assert result.paths == [] and path.read_text() == original


def test_dry_run_and_quarantined_nyan_never_write(tmp_path):
    path = _record(tmp_path, "example", "owner/example", {"stars": 1, "as_of": "2026-09-20"})
    nyan = _record(tmp_path, "nyan", "TeMPOraL/nyan-mode", {"stars": 1, "as_of": "2026-09-20"})
    original = path.read_text()
    ctx, calls = _ctx(tmp_path, {"full_name": "owner/example", "id": 123,
                                "stargazers_count": 30, "forks_count": 3}, dry_run=True)
    result = refresh.run(ctx)
    assert len(calls) == 1 and "nyan-mode" not in str(calls)
    assert len(result.would_write) == 1 and result.paths == []
    assert path.read_text() == original and nyan.exists()


def test_below_floor_count_is_deferred_without_aborting_other_tick_work(tmp_path):
    path = _record(tmp_path, "example", "owner/example",
                   {"stars": 30, "forks": 2, "as_of": "2026-09-20"})
    original = path.read_text()
    ctx, _ = _ctx(tmp_path, {"full_name": "owner/example", "id": 123,
                            "stargazers_count": 10, "forks_count": 2})
    result = refresh.run(ctx)
    assert result.paths == [] and "1 below-floor deferred" in result.summary
    assert path.read_text() == original


def test_fresh_snapshot_and_low_budget_make_no_upstream_call(tmp_path):
    path = _record(tmp_path, "example", "owner/example",
                   {"stars": 10, "forks": 2, "github_as_of": "2026-11-05T12:00:00Z",
                    "as_of": "2026-11-05"})
    original = path.read_text()
    ctx, calls = _ctx(tmp_path, {"full_name": "owner/example", "id": 123,
                                "stargazers_count": 11, "forks_count": 3})
    assert refresh.run(ctx).paths == [] and calls == []
    ctx.budget = Budget(max_calls=8)
    ctx.now = NOW.replace(day=7)
    assert refresh.run(ctx).paths == [] and calls == [] and path.read_text() == original


def test_slice_is_bounded_and_a_stable_catalog_is_covered(tmp_path):
    for i in range(145):
        _record(tmp_path, f"fw-{i:03}", f"owner/repo-{i:03}", {"stars": 1, "as_of": "2026-09-20"})
    seen = set()
    for hour in range(24):
        ctx, calls = _ctx(tmp_path, {"full_name": "unused", "id": 1,
                                    "stargazers_count": 1, "forks_count": 0}, dry_run=True)
        ctx.now = NOW.replace(hour=hour)
        refresh.run(ctx)
        assert len(calls) <= refresh.MAX_REPOS_PER_TICK
        seen.update(call[1] for call in calls)
    assert len(seen) == 145


def _pending_ctx(root: Path, response: dict):
    ctx, calls = _ctx(root, response)
    ctx.pending = pending_prs.build(
        [{"number": 1511, "headRefName": "jr/tick-20261107-0300", "files": [{"path": "data/firmware/held/firmware.md"}]}],
        [{"number": 1478, "headRefName": "jr/tick-20261106-0900", "mergedAt": None, "closedAt": "2026-11-05T00:00:00Z",
          "files": [{"path": "data/firmware/vetoed/signals.json"}]}], NOW)
    return ctx, calls


def test_a_record_an_open_tick_pr_holds_is_deferred_with_no_upstream_call(tmp_path):
    """jr/pending_prs.py: an OPEN tick PR already changes this firmware.md — a second edit would
    conflict with it, so the refresh waits for that PR."""
    held = _record(tmp_path, "held", "owner/held", {"stars": 10, "forks": 2, "as_of": "2026-09-20"})
    original = held.read_text()
    ctx, calls = _pending_ctx(tmp_path, {"full_name": "owner/held", "id": 7, "stargazers_count": 11, "forks_count": 3})
    result = refresh.run(ctx)
    assert held.read_text() == original and calls == [] and result.paths == []
    assert "0 current" in result.summary and "1 pending deferred" in result.summary


def test_a_vetoed_record_is_still_refreshed(tmp_path):
    """A veto rejected a proposal (mapped signals), not the catalogued record's counts."""
    vetoed = _record(tmp_path, "vetoed", "owner/vetoed", {"stars": 100, "forks": 2, "as_of": "2026-09-20"})
    ctx, _ = _pending_ctx(tmp_path, {"full_name": "owner/vetoed", "id": 7, "stargazers_count": 101, "forks_count": 3})
    result = refresh.run(ctx)
    assert result.paths == ["data/firmware/vetoed/firmware.md"] and _fm(vetoed)["popularity"]["stars"] == 101
    assert "pending deferred" not in result.summary
