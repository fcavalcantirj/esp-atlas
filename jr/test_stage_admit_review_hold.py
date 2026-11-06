"""The admit gate holds a target whose owner-review decision is live and unchanged
(SPEC-jr-review-routing.md §5): no second review item, no device-evidence re-fetch; genuinely new
evidence or an expired decision is reconsidered. Fake network only (the fake gh of
test_stage_admit), ledgers under tmp_path.

Run: cd jr && python3 -m pytest test_stage_admit_review_hold.py -v
"""
from __future__ import annotations

from datetime import timedelta

import memory
import review_memory
import stage_admit
import tools
from test_stage_admit import NOW, _ctx, _entry, _meta, root  # noqa: F401 — root is a fixture
from test_stage_admit_device_gate import RELEASES, TREE, _raw, _tree

ZAP = "z/zapkit"


def _metas(pushed="2026-09-01T00:00:00Z", stars=40):
    meta = _meta(ZAP, stars=stars, description="A Cardputer tool", rid=24)
    meta["pushed_at"] = pushed
    return {"repos/z/zapkit": meta, TREE.format(ZAP): _tree("README.md", "zapkit/zapkit.ino"), RELEASES.format(ZAP): []}


def _run(root, monkeypatch, metas, now=NOW, dry_run=False):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])
    ctx = _ctx(root, metas=metas, dry_run=dry_run)
    ctx.now = now
    calls = []
    inner = ctx.gh

    def gh(*a):
        calls.append(a[1] if len(a) > 1 else a)
        return inner(*a)
    ctx.gh = gh
    return stage_admit.run(ctx, budget=3, raw=_raw({})), calls


def _rec(root):
    return memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["zapkit"]


def test_a_needs_review_target_is_remembered_as_a_raised_decision_with_its_evidence(root, monkeypatch):
    res, _ = _run(root, monkeypatch, _metas())
    [item] = res.review
    rec = _rec(root)
    assert rec["status"] == "rejected" and rec["reason"].startswith("needs_review_target:")
    assert rec["review"]["outcome"] == "raised" and rec["review"]["evidence"]["stars"] == 40
    assert item["repo_id"] == 24 and item["evidence_rev"] == rec["review"]["evidence_rev"]
    assert item["reason"] == rec["reason"]


def test_an_unchanged_target_is_held_no_review_item_and_no_build_evidence_refetch(root, monkeypatch):
    _run(root, monkeypatch, _metas())
    before = _rec(root)
    res, calls = _run(root, monkeypatch, _metas(stars=41), now=NOW + timedelta(hours=1))   # one star is not news
    assert res.review == [] and "needs_review_target" not in res.rejects
    assert calls == ["repos/z/zapkit"]                     # the meta fetch only: the gate never re-runs
    assert "review already raised: z/zapkit" in res.summary
    assert _rec(root) == before                            # nothing rewritten, expiry not refreshed


def test_a_legacy_decision_without_a_revision_is_held_and_its_revision_backfilled(root, monkeypatch):
    path = root / "jr" / "proposed_ledger.json"
    memory.record_review_decision("zapkit", ZAP, "needs_review_target: owner review raised in #1490",
                                  pr_ref="#1490", outcome="open", raised_at=NOW - timedelta(hours=3),
                                  path=path, now=NOW)
    res, _ = _run(root, monkeypatch, _metas())
    assert res.review == []
    rec = _rec(root)
    assert rec["review"]["evidence_rev"] and rec["review"]["pr_ref"] == "#1490" and rec["repo_id"] == 24
    assert rec["expires"] == (NOW - timedelta(hours=3) + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)).isoformat()


def test_a_new_push_is_new_evidence_the_target_is_reconsidered_and_re_raised(root, monkeypatch):
    _run(root, monkeypatch, _metas())
    old = _rec(root)
    res, calls = _run(root, monkeypatch, _metas(pushed="2026-09-06T00:00:00Z"), now=NOW + timedelta(hours=1))
    [item] = res.review                                    # reconsidered — and NOT rejected as its own duplicate_of
    assert TREE.format(ZAP) in calls and item["evidence_rev"] != old["review"]["evidence_rev"]
    rec = _rec(root)
    assert rec["review"]["evidence_rev"] == item["evidence_rev"] and rec["history"][-1]["review"] == old["review"]


def test_an_expired_decision_is_reconsidered(root, monkeypatch):
    _run(root, monkeypatch, _metas())
    later = NOW + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS, hours=1)
    memory.expire(path=root / "jr" / "proposed_ledger.json", now=later)
    res, _ = _run(root, monkeypatch, _metas(), now=later)
    assert [i["repo"] for i in res.review] == [ZAP]


def test_a_held_target_in_a_dry_run_writes_nothing(root, monkeypatch):
    _run(root, monkeypatch, _metas())
    before = (root / "jr" / "proposed_ledger.json").read_text()
    res, _ = _run(root, monkeypatch, _metas(), now=NOW + timedelta(hours=1), dry_run=True)
    assert res.review == [] and (root / "jr" / "proposed_ledger.json").read_text() == before


def test_a_plain_live_rejection_still_skips_before_any_fetch(root, monkeypatch):
    memory.record_rejected("zapkit", ZAP, "below_floor: 1 stars / 0 forks", ttl_days=30, repo_id=24,
                           path=root / "jr" / "proposed_ledger.json", now=NOW)
    res, calls = _run(root, monkeypatch, _metas())
    assert calls == [] and res.review == []


def test_a_live_decision_held_through_its_repo_id_after_a_rename(root, monkeypatch):
    path = root / "jr" / "proposed_ledger.json"
    memory.record_review_decision("zapkit-old", "z/zapkit-old", "needs_review_target: x", repo_id=24,
                                  evidence_rev=review_memory.evidence_rev(review_memory.evidence(
                                      {"stars": 40, "forks": 0, "homepage": None, "pushed_at": "2026-09-01T00:00:00Z"},
                                      downloads=100)), path=path, now=NOW)
    res, calls = _run(root, monkeypatch, _metas())
    assert res.review == [] and calls == ["repos/z/zapkit"]
