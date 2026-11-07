"""Offline scheduled PR-to-deployed-cache delivery checks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import popularity_delivery as delivery
import popularity_run
import publish
from test_stage_popularity_refresh import _record

NOW = datetime(2026, 11, 7, 3, tzinfo=timezone.utc)
URL = "https://github.com/o/r/pull/8"
HEAD = "b" * 40
MERGE = "c" * 40
DEPLOY = "d" * 40


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
            return 200, (f'<p class="firmware-popularity">{stars} stars · 5 forks '
                         '<span>GitHub repo · as of 2026-11-07 02:00 UTC</span></p>').encode()
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
