"""Offline scheduled PR-to-deployed-cache delivery checks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import popularity_delivery as delivery
import popularity_run
import publish
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 3, tzinfo=timezone.utc)
URL = "https://github.com/o/r/pull/8"
HEAD = "b" * 40
MERGE = "c" * 40
DEPLOY = "d" * 40


def _page(stars, forks, date="2026-11-07 02:00 UTC"):
    return (f'<p class="firmware-popularity"><span class="firmware-popularity-figure">{stars}</span> stars'
            f' · <span class="firmware-popularity-figure">{forks}</span> forks'
            f'<span>GitHub repo · as of {date}</span></p>').encode()


def _seed(path, *, state="pending"):
    popularity_run._write_state(path, {"deliveries": [{
        "pr_url": URL, "head_sha": HEAD, "state": state,
        "samples": [{"id": "fw", "stars": 40, "forks": 5,
                     "github_as_of": "2026-11-07T02:00:00Z"}],
        "merge_sha": MERGE if state != "pending" else None}]})


def _reconcile(path, gh, git, fetch, revalidate):
    return delivery.reconcile(path, load_state=popularity_run._load_state,
        write_state=popularity_run._write_state, gh=gh, git=git, secret="secret",
        fetch=fetch, revalidate=revalidate, now=NOW)


def test_pending_pr_does_not_claim_deployment_or_invalidate(tmp_path):
    path = tmp_path / "state.json"
    _seed(path)
    def gh(*args):
        return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "OPEN", "headRefOid": HEAD}))
    def no(*args):
        raise AssertionError("no deployment or revalidation before merge")
    rows = _reconcile(path, gh, no, no, no)
    assert rows[0]["state"] == "pending"
    assert "awaiting guarded merge" in rows[0]["reason"]


def test_merged_pr_waits_for_deployed_revision_then_invalidates_and_reads_back(tmp_path):
    path = tmp_path / "state.json"
    _seed(path)
    remote = {"revision": "a" * 40, "purge_ok": True, "page_stale": False}
    calls = []
    def gh(*args):
        return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "MERGED", "mergedAt": NOW.isoformat(),
            "headRefOid": HEAD, "mergeCommit": {"oid": MERGE}}))
    def git(*args):
        calls.append(args)
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if args[3] == DEPLOY else 1)
        return SimpleNamespace(returncode=0)
    def fetch(url):
        calls.append(("GET", url))
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": remote["revision"]}]}).encode()
        if url.endswith("/api/firmware/fw"):
            return 200, json.dumps({"popularity": {"stars": 40, "forks": 5,
                "github_as_of": "2026-11-07T02:00:00Z"}}).encode()
        if url.endswith("/firmware/fw"):
            stars = 30 if remote["page_stale"] else 40
            return 200, _page(stars, 5)
        raise AssertionError(url)
    def revalidate(secret):
        calls.append(("POST", "/api/revalidate"))
        return {"ok": remote["purge_ok"], "status": 200 if remote["purge_ok"] else 503,
                "body": '{"revalidated":true,"tag":"catalog"}' if remote["purge_ok"] else "{}"}

    rows = _reconcile(path, gh, git, fetch, revalidate)
    assert rows[0]["state"] == "merged" and "awaiting deployed" in rows[0]["reason"]
    assert not any(c[0] == "POST" for c in calls)
    remote["revision"] = DEPLOY
    remote["purge_ok"] = False
    rows = _reconcile(path, gh, git, fetch, revalidate)
    assert rows[0]["state"] == "deployed" and "invalidation failed" in rows[0]["reason"]
    remote["purge_ok"] = True
    remote["page_stale"] = True
    rows = _reconcile(path, gh, git, fetch, revalidate)
    assert rows[0]["state"] == "invalidated" and "rendered page differs" in rows[0]["reason"]
    remote["page_stale"] = False
    rows = _reconcile(path, gh, git, fetch, revalidate)
    assert rows[0]["state"] == "readback_verified"
    saved = popularity_run._load_state(path)["deliveries"][0]
    assert saved["readback"] == {"deployed_revision": DEPLOY, "sample_ids": ["fw"]}
    assert saved["revalidation"] == {"status": 200, "ok": True}
    assert sum(c[0] == "POST" for c in calls) == 3
    assert any(c[:2] == ("GET", "https://esp-atlas.com/firmware/fw") for c in calls)


def test_revalidation_requires_the_catalog_tag_response():
    assert delivery._purge_confirmed({"ok": True, "status": 200,
        "body": '{"revalidated":true,"tag":"catalog"}'})
    assert not delivery._purge_confirmed({"ok": True, "status": 200, "body": "<html>login</html>"})
    assert not delivery._purge_confirmed({"ok": True, "status": 200,
        "body": '{"revalidated":true,"tag":"other"}'})


@pytest.mark.parametrize("expected,page_counts,passes", [
    ((40, 5), (140, 15), False),
    ((40, 5), (40, 15), False),
    ((40, 5), (140, 5), False),
    ((0, 0), (10, 10), False),
    ((0, 0), (0, 0), True),
    ((40, 5), (40, 5), True),
])
def test_rendered_readback_compares_full_numeric_fields_including_zero(expected, page_counts, passes):
    def git(*args):
        return SimpleNamespace(returncode=0)
    def fetch(url):
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": DEPLOY}]}).encode()
        if url.endswith("/api/firmware/fw"):
            return 200, json.dumps({"popularity": {"stars": expected[0], "forks": expected[1],
                "github_as_of": "2026-11-07T02:00:00Z"}}).encode()
        if url.endswith("/firmware/fw"):
            return 200, _page(*page_counts)
        raise AssertionError(url)
    ok, _ = delivery._readback(fetch, git, MERGE,
        [{"id": "fw", "stars": expected[0], "forks": expected[1],
          "github_as_of": "2026-11-07T02:00:00Z"}])
    assert ok is passes


def test_newer_merged_snapshot_supersedes_stale_older_sample_without_certifying_it(tmp_path):
    path = tmp_path / "state.json"
    newer_merge = "e" * 40
    popularity_run._write_state(path, {"deliveries": [
        {"pr_url": URL, "head_sha": HEAD, "state": "invalidated", "merge_sha": MERGE,
         "samples": [{"id": "fw", "stars": 40, "forks": 5,
                      "github_as_of": "2026-11-07T02:00:00Z"}], "changed_ids": ["fw"]},
        {"pr_url": "https://github.com/o/r/pull/9", "head_sha": "f" * 40,
         "state": "merged", "merge_sha": newer_merge, "changed_ids": ["fw"],
         "samples": [{"id": "fw", "stars": 41, "forks": 5,
                      "github_as_of": "2026-11-07T03:00:00Z"}]},
    ]})
    def gh(*args):
        raise AssertionError("both PRs are already known merged")
    def git(*args):
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if (args[2], args[3]) in
                {(MERGE, newer_merge), (newer_merge, DEPLOY)} else 1)
        return SimpleNamespace(returncode=0)
    def fetch(url):
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": DEPLOY}]}).encode()
        if url.endswith("/api/firmware/fw"):
            return 200, json.dumps({"popularity": {"stars": 41, "forks": 5,
                "github_as_of": "2026-11-07T03:00:00Z"}}).encode()
        if url.endswith("/firmware/fw"):
            return 200, _page(41, 5, "2026-11-07 03:00 UTC")
        raise AssertionError(url)
    def purge(secret):
        return {"ok": True, "status": 200, "body": '{"revalidated":true,"tag":"catalog"}'}
    first = _reconcile(path, gh, git, fetch, purge)
    assert [r["state"] for r in first] == ["invalidated", "merged"]
    second = _reconcile(path, gh, git, fetch, purge)
    assert [r["state"] for r in second] == ["invalidated", "readback_verified"]
    rows = _reconcile(path, gh, git, fetch, purge)
    assert [r["state"] for r in rows] == ["superseded", "readback_verified"]
    saved = popularity_run._load_state(path)["deliveries"]
    assert saved[0]["superseded_by"] == "https://github.com/o/r/pull/9"
    assert "readback" not in saved[0]


def test_live_delivery_schedule_is_fair_across_restarts_without_supersession_proof(tmp_path):
    path = tmp_path / "state.json"
    newer_merge = "e" * 40
    popularity_run._write_state(path, {"deliveries": [
        {"pr_url": URL, "head_sha": HEAD, "state": "invalidated", "merge_sha": MERGE,
         "samples": [{"id": "fw", "stars": 40, "forks": 5,
                      "github_as_of": "2026-11-07T02:00:00Z"}]},
        {"pr_url": "https://github.com/o/r/pull/9", "head_sha": "f" * 40,
         "state": "merged", "merge_sha": newer_merge, "changed_ids": ["other"],
         "samples": [{"id": "other", "stars": 41, "forks": 5,
                      "github_as_of": "2026-11-07T03:00:00Z"}]},
    ]})
    def gh(*args):
        raise AssertionError("both PRs are already known merged")
    def git(*args):
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if args[2] == newer_merge and args[3] == DEPLOY else 1)
        return SimpleNamespace(returncode=0)
    def fetch(url):
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": DEPLOY}]}).encode()
        if url.endswith("/api/firmware/other"):
            return 200, json.dumps({"popularity": {"stars": 41, "forks": 5,
                "github_as_of": "2026-11-07T03:00:00Z"}}).encode()
        if url.endswith("/firmware/other"):
            return 200, _page(41, 5, "2026-11-07 03:00 UTC")
        if url.endswith("/api/firmware/fw"):
            return 200, json.dumps({"popularity": {"stars": 41, "forks": 5,
                "github_as_of": "2026-11-07T03:00:00Z"}}).encode()
        raise AssertionError(url)
    def purge(secret):
        return {"ok": True, "status": 200, "body": '{"revalidated":true,"tag":"catalog"}'}
    first = _reconcile(path, gh, git, fetch, purge)
    assert [r["state"] for r in first] == ["invalidated", "merged"]
    second = _reconcile(path, gh, git, fetch, purge)  # reloads persisted sequence
    assert [r["state"] for r in second] == ["invalidated", "readback_verified"]
    assert popularity_run._load_state(path)["delivery_live_sequence"] == 2
    state = popularity_run._load_state(path)
    state["deliveries"].append({"pr_url": "https://github.com/o/r/pull/10",
        "head_sha": "1" * 40, "state": "merged", "merge_sha": "2" * 40,
        "changed_ids": ["unrelated"], "samples": [],
        "live_check_sequence": state["delivery_live_sequence"]})
    popularity_run._write_state(path, state)
    third = _reconcile(path, gh, git, fetch, purge)
    assert [r["state"] for r in third] == ["invalidated", "readback_verified", "merged"]
    state = popularity_run._load_state(path)
    assert state["deliveries"][0]["live_check_sequence"] == 3
    assert state["deliveries"][2]["live_check_sequence"] == 2


def test_steady_one_deployment_lag_still_verifies_ready_predecessors(tmp_path):
    path = tmp_path / "state.json"
    live = {"revision": 1}
    calls = []

    def row(number, sequence):
        return {"pr_url": f"https://github.com/o/r/pull/{number}",
                "head_sha": "a" * 39 + str(number), "state": "merged",
                "merge_sha": str(number) * 40, "changed_ids": ["fw"],
                "live_check_sequence": sequence,
                "samples": [{"id": "fw", "stars": number * 10, "forks": 5,
                             "github_as_of": f"2026-11-07T0{number}:00:00Z"}]}

    popularity_run._write_state(path, {"deliveries": [row(2, 0)]})

    def gh(*args):
        raise AssertionError("all PRs already merged")

    def git(*args):
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if int(args[2][0]) <= int(args[3][0]) else 1)
        return SimpleNamespace(returncode=0)

    def fetch(url):
        number = live["revision"]
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": str(number) * 40}]}).encode()
        if url.endswith("/api/firmware/fw"):
            calls.append(("api", number))
            return 200, json.dumps({"popularity": {"stars": number * 10, "forks": 5,
                "github_as_of": f"2026-11-07T0{number}:00:00Z"}}).encode()
        if url.endswith("/firmware/fw"):
            calls.append(("page", number))
            return 200, _page(number * 10, 5, f"2026-11-07 0{number}:00 UTC")
        raise AssertionError(url)

    def purge(secret):
        calls.append(("purge", live["revision"]))
        return {"ok": True, "status": 200, "body": '{"revalidated":true,"tag":"catalog"}'}

    first = _reconcile(path, gh, git, fetch, purge)  # merge 2; deployed 1
    assert [r["state"] for r in first] == ["merged"] and not calls
    state = popularity_run._load_state(path)
    state["deliveries"].append(row(3, state["delivery_live_sequence"]))
    popularity_run._write_state(path, state)
    live["revision"] = 2
    second = _reconcile(path, gh, git, fetch, purge)  # merge 3; deployed 2
    assert [r["state"] for r in second] == ["readback_verified", "merged"]
    state = popularity_run._load_state(path)
    state["deliveries"].append(row(4, state["delivery_live_sequence"]))
    popularity_run._write_state(path, state)
    live["revision"] = 3
    third = _reconcile(path, gh, git, fetch, purge)  # merge 4; deployed 3
    assert [r["state"] for r in third] == ["readback_verified", "readback_verified", "merged"]
    assert calls == [("purge", 2), ("api", 2), ("page", 2),
                     ("purge", 3), ("api", 3), ("page", 3)]


def test_transient_purge_failure_then_continuous_new_deployments_still_verifies(tmp_path):
    path = tmp_path / "state.json"
    live = {"number": 1}
    calls = {"purges": 0, "api": 0}

    def sha(number):
        return f"{number:040x}"

    def register_merged_publication(number):
        state = popularity_run._load_state(path)
        result = publish.PublishResult(True, branch=f"jr/popularity-20261107-{number:04d}",
            commit=sha(100 + number), pr_url=f"https://github.com/o/r/pull/{number}",
            paths=["data/firmware/fw/firmware.md"])
        samples = [{"id": "fw", "stars": number * 10, "forks": 5,
                    "github_as_of": f"2026-11-{number:02d}T02:00:00Z"}]
        delivery.register(state, result, samples, NOW,
                          f"docs/telemetry/popularity/tick-{number}.json")
        if number > 1:
            assert state["deliveries"][-1]["live_check_sequence"] > 0
            assert state["deliveries"][-1]["live_check_attempted"] is False
        popularity_run._write_state(path, state)

    register_merged_publication(1)

    def gh(*args):
        assert args[:2] == ("pr", "view")
        number = int(args[2].rsplit("/", 1)[-1])
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "state": "MERGED", "headRefOid": sha(100 + number),
            "mergedAt": NOW.isoformat(), "mergeCommit": {"oid": sha(number)}}))

    def git(*args):
        if args[:2] == ("merge-base", "--is-ancestor"):
            return SimpleNamespace(returncode=0 if int(args[2], 16) <= int(args[3], 16) else 1)
        return SimpleNamespace(returncode=0)

    def fetch(url):
        number = live["number"]
        if url.endswith("/api/status"):
            return 200, json.dumps({"components": [{"name": "Deploy", "revision": sha(number)}]}).encode()
        if url.endswith("/api/firmware/fw"):
            calls["api"] += 1
            return 200, json.dumps({"popularity": {"stars": number * 10, "forks": 5,
                "github_as_of": f"2026-11-{number:02d}T02:00:00Z"}}).encode()
        if url.endswith("/firmware/fw"):
            return 200, _page(number * 10, 5, f"2026-11-{number:02d} 02:00 UTC")
        raise AssertionError(url)

    def purge(secret):
        calls["purges"] += 1
        ok = calls["purges"] != 1
        return {"ok": ok, "status": 200 if ok else 503,
                "body": '{"revalidated":true,"tag":"catalog"}' if ok else "{}"}

    for number in range(1, 9):
        if number > 1:
            register_merged_publication(number)  # real registration, persisted before next tick
            live["number"] = number
        _reconcile(path, gh, git, fetch, purge)

    saved = popularity_run._load_state(path)
    states = [item["state"] for item in saved["deliveries"]]
    assert states[0] == "superseded" and "readback" not in saved["deliveries"][0]
    assert states[-1] == "readback_verified"
    assert states.count("readback_verified") >= 1
    assert sum(state in {"merged", "deployed", "invalidated"} for state in states) <= 1
    assert calls["purges"] >= 2 and calls["api"] >= 1
    assert saved["delivery_live_sequence"] == 8


def test_register_supersedes_only_unmerged_head_and_samples_changed_record(tmp_path):
    path = _record(tmp_path, "fw", "owner/repo-001", {"stars": 40, "forks": 5,
                    "github_as_of": "2026-11-07T02:00:00Z"})
    samples = delivery.expected_samples(tmp_path, [str(path.relative_to(tmp_path))])
    assert samples == [{"id": "fw", "stars": 40, "forks": 5,
                        "github_as_of": "2026-11-07T02:00:00Z"}]
    state = {"deliveries": [{"pr_url": URL, "head_sha": "a" * 40, "state": "pending"},
                            {"pr_url": "other", "head_sha": "z" * 40, "state": "merged"}]}
    result = publish.PublishResult(True, branch="jr/popularity-20261107-0200", commit=HEAD,
        pr_url=URL, paths=[str(path.relative_to(tmp_path))])
    delivery.register(state, result, samples, NOW, "docs/telemetry/popularity/2026-11-07T02.json")
    assert [row["state"] for row in state["deliveries"]] == ["superseded", "merged", "pending"]
    assert state["deliveries"][-1]["changed_records"] == 1
    assert state["deliveries"][-1]["live_check_sequence"] == 0
