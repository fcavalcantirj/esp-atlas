"""Tests for jr/memory.py — ledger v2: TTL'd decisions, repo_id lookup, PR reconciliation.

Every test writes a throwaway ledger under tmp_path; the real jr/proposed_ledger.json is only
ever READ (one test loads it to prove v1 records survive v2 untouched).

Run: cd jr && python3 -m pytest test_memory.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import ledger
import memory

NOW = datetime(2026, 9, 5, 3, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "proposed_ledger.json"


# --- TTL'd rejections -----------------------------------------------------------------------

def test_record_rejected_with_ttl_sets_expires(path):
    memory.record_rejected("make-ap", "big-bratan/make-ap", "below floor: 10 stars / 0 forks",
                           ttl_days=memory.FLOOR_REJECT_DAYS, path=path, now=NOW)
    rec = ledger.load_ledger(path)["by_id"]["make-ap"]
    assert rec["status"] == "rejected"
    assert rec["reason"] == "below floor: 10 stars / 0 forks"
    assert rec["expires"] == (NOW + timedelta(days=30)).isoformat()
    assert rec["timestamp"] == NOW.isoformat()


def test_record_rejected_permanent_has_no_expires(path):
    memory.record_rejected("firmware", "BruceDevices/firmware", "duplicate_of bruce", path=path, now=NOW)
    rec = ledger.load_ledger(path)["by_id"]["firmware"]
    assert "expires" not in rec
    assert rec["repo"] == "brucedevices/firmware"          # lower-cased like ledger.py
    led = memory.load(path)
    assert memory.is_blocked(led, firmware_id="firmware", now=NOW + timedelta(days=3650))


def test_ttl_rejection_blocks_until_it_expires_even_before_expire_runs(path):
    memory.record_rejected("x", "o/x", "unresolved", ttl_days=memory.UNRESOLVED_REJECT_DAYS,
                           path=path, now=NOW)
    led = memory.load(path)
    assert memory.is_blocked(led, repo="o/x", now=NOW + timedelta(days=6, hours=23))
    assert not memory.is_blocked(led, repo="o/x", now=NOW + timedelta(days=7))
    # ledger.py's own view has no clock and still says blocked — memory's is the one gates use
    assert ledger.is_blocked(led, repo="o/x")


def test_expire_flips_overdue_records_and_keeps_history(path):
    memory.record_rejected("old", "o/old", "below floor", ttl_days=30, path=path, now=NOW)
    memory.record_seen("note", "o/note", "scored 12 stars", ttl_days=30, path=path, now=NOW)
    memory.record_rejected("human", "o/human", "PR closed unmerged", path=path, now=NOW)   # permanent
    memory.record_rejected("fresh", "o/fresh", "archived", ttl_days=90, path=path, now=NOW)

    flipped = memory.expire(path=path, now=NOW + timedelta(days=31))

    assert sorted(flipped) == ["note", "old"]
    led = memory.load(path)
    assert led["by_id"]["old"]["status"] == "expired"
    assert led["by_id"]["old"]["reason"] == "below floor"           # history kept
    assert led["by_id"]["note"]["status"] == "expired"
    assert led["by_id"]["human"]["status"] == "rejected"            # permanent, untouched
    assert led["by_id"]["fresh"]["status"] == "rejected"            # 90 d, not yet
    # expired reads as absent to every gate, in both memory's and ledger's view
    assert not memory.is_blocked(led, firmware_id="old")
    assert not memory.is_seen(led, firmware_id="note")
    assert not ledger.is_blocked(led, firmware_id="old")
    assert not ledger.is_seen(led, firmware_id="note")


def test_expire_writes_nothing_when_nothing_is_due(path):
    memory.record_rejected("a", "o/a", "archived", ttl_days=90, path=path, now=NOW)
    before = path.read_text()
    assert memory.expire(path=path, now=NOW + timedelta(days=1)) == []
    assert path.read_text() == before


def test_seen_default_ttl_is_thirty_days(path):
    memory.record_seen("s", "o/s", path=path, now=NOW)
    rec = ledger.load_ledger(path)["by_id"]["s"]
    assert rec["status"] == "seen"
    assert rec["expires"] == (NOW + timedelta(days=memory.SEEN_TTL_DAYS)).isoformat()
    led = memory.load(path)
    assert memory.is_seen(led, repo="o/s", now=NOW + timedelta(days=29))
    assert not memory.is_seen(led, repo="o/s", now=NOW + timedelta(days=30))


# --- repo_id + evidence_url ------------------------------------------------------------------

def test_by_repo_id_is_derived_and_survives_renames(path):
    memory.record_rejected("firmware", "brucedevices/firmware", "duplicate_of bruce",
                           repo_id=795166961, path=path, now=NOW)
    led = memory.load(path)
    assert led["by_repo_id"] == {795166961: "firmware"}
    # the persisted file carries repo_id on the record but NO by_repo_id index
    raw = json.loads(path.read_text())
    assert "by_repo_id" not in raw
    assert raw["by_id"]["firmware"]["repo_id"] == 795166961
    # a renamed repo is still found by id when the name no longer matches
    assert memory.lookup(led, repo="pr3y/Bruce", repo_id=795166961)["id"] == "firmware"
    assert memory.is_blocked(led, repo="pr3y/Bruce", repo_id=795166961, now=NOW)


def test_evidence_url_is_kept_verbatim(path):
    url = "https://github.com/ruvnet/ruview/releases/tag/v0.8.8-esp32"
    memory.record_proposed("ruview", "ruvnet/ruview", pr_ref="https://github.com/x/y/pull/9",
                           repo_id=1, evidence_url=url, path=path, now=NOW)
    rec = ledger.load_ledger(path)["by_id"]["ruview"]
    assert rec["evidence_url"] == url
    assert rec["status"] == "proposed" and "expires" not in rec
    assert memory.is_blocked(memory.load(path), firmware_id="ruview", now=NOW + timedelta(days=999))


# --- reconciliation ---------------------------------------------------------------------------

def test_reconcile_removed_turns_a_vanished_merged_id_into_a_permanent_rejection(path):
    memory.record_proposed("gone", "o/gone", path=path, now=NOW)
    ledger.update_status("gone", "merged", path=path)
    memory.record_proposed("still", "o/still", path=path, now=NOW)
    ledger.update_status("still", "merged", path=path)

    flipped = memory.reconcile_removed({"still", "unrelated"}, path=path, now=NOW)

    assert flipped == ["gone"]
    led = memory.load(path)
    assert led["by_id"]["gone"]["status"] == "rejected"
    assert led["by_id"]["gone"]["reason"] == "removed from catalog"
    assert "expires" not in led["by_id"]["gone"]
    assert led["by_id"]["still"]["status"] == "merged"
    assert memory.is_blocked(led, firmware_id="gone", now=NOW + timedelta(days=3650))


def test_reconcile_prs_settles_closed_and_merged_leaves_open(path):
    memory.record_proposed("a", "o/a", pr_ref="https://github.com/x/y/pull/1", path=path, now=NOW)
    memory.record_proposed("b", "o/b", pr_ref="https://github.com/x/y/pull/2", path=path, now=NOW)
    memory.record_proposed("c", "o/c", pr_ref="https://github.com/x/y/pull/3", path=path, now=NOW)
    memory.record_proposed("d", "o/d", pr_ref=None, path=path, now=NOW)
    states = {"https://github.com/x/y/pull/1": "closed", "https://github.com/x/y/pull/2": "merged",
              "https://github.com/x/y/pull/3": "open"}

    out = memory.reconcile_prs(lambda ref: states[ref], path=path, now=NOW)

    assert out == {"merged": ["b"], "rejected": ["a"]}
    led = memory.load(path)
    assert led["by_id"]["a"]["status"] == "rejected"
    assert led["by_id"]["a"]["reason"] == "PR closed unmerged: https://github.com/x/y/pull/1"
    assert "expires" not in led["by_id"]["a"]                        # human veto is permanent
    assert led["by_id"]["b"]["status"] == "merged"
    assert led["by_id"]["c"]["status"] == "proposed"
    assert led["by_id"]["d"]["status"] == "proposed"                 # no pr_ref: never asked


def test_gh_pr_state_maps_gh_output_and_never_raises():
    class P:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out
    assert memory.gh_pr_state("u", gh=lambda *a: P(0, '{"state":"MERGED","mergedAt":"2026-09-05T02:38:00Z"}')) == "merged"
    assert memory.gh_pr_state("u", gh=lambda *a: P(0, '{"state":"CLOSED","mergedAt":null}')) == "closed"
    assert memory.gh_pr_state("u", gh=lambda *a: P(0, '{"state":"OPEN","mergedAt":null}')) == "open"
    assert memory.gh_pr_state("u", gh=lambda *a: P(1, "")) == "unknown"
    assert memory.gh_pr_state("u", gh=lambda *a: P(0, "not json")) == "unknown"


# --- compatibility with v1 records and the real ledger ----------------------------------------

def test_v1_records_without_v2_fields_keep_their_semantics(path):
    ledger.record_proposed("p", "o/p", pr_ref="https://github.com/x/y/pull/5", path=path)
    ledger.mark_rejected("r", path=path)          # no-op: never proposed
    ledger.record_proposed("r", "o/r", path=path)
    ledger.mark_rejected("r", path=path, reason="seeded")
    ledger.record_seen("s", "o/s", path=path)     # v1 seen: no expires → never expires

    led = memory.load(path)
    far = NOW + timedelta(days=3650)
    assert memory.is_blocked(led, firmware_id="p", now=far)
    assert memory.is_blocked(led, firmware_id="r", now=far)
    assert memory.is_seen(led, firmware_id="s", now=far)
    assert led["by_repo_id"] == {}
    assert memory.expire(path=path, now=far) == []


def test_real_ledger_loads_and_is_untouched_by_a_load():
    """Read-only on the real file: 130 records with statuses seen/merged/rejected must load,
    derive an (empty or partial) by_repo_id, and every record must remain blocking/seen exactly
    as ledger.py sees it — the drain's prefilter and the tick must agree."""
    before = memory.DEFAULT_LEDGER_PATH.read_text()
    led = memory.load()
    assert len(led["by_id"]) >= 100
    for fid, rec in led["by_id"].items():
        assert rec["status"] in ledger.STATUSES, fid
        if "expires" not in rec:
            assert memory.is_blocked(led, firmware_id=fid, now=NOW) == ledger.is_blocked(led, firmware_id=fid)
            assert memory.is_seen(led, firmware_id=fid, now=NOW) == ledger.is_seen(led, firmware_id=fid)
    assert memory.DEFAULT_LEDGER_PATH.read_text() == before


def test_staged_paths_points_at_the_ledger_inside_the_repo():
    assert memory.staged_paths() == ["jr/proposed_ledger.json"]
