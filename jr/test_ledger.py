"""EspAtlas Jr — pytest for the proposed-ledger (jr/ledger.py).

Covers: load_ledger on a missing/empty/corrupt file, record_proposed writing a dual-indexed
(by_id + by_repo) record with a PR ref, update_status/mark_rejected transitioning an existing
record (and no-op on an unknown id), is_blocked/lookup by either id or repo, and
reconcile_merged flipping proposed ids to merged once they land in the real catalogue. Every
test uses tmp_path — the real jr/proposed_ledger.json is never read or written.

Run: cd jr && python3 -m pytest test_ledger.py -v
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402


@pytest.fixture
def path(tmp_path):
    return tmp_path / "proposed_ledger.json"


# ─────────────────────────── load_ledger ───────────────────────────

def test_load_ledger_missing_file_is_empty(path):
    assert ledger.load_ledger(path) == {"by_id": {}, "by_repo": {}}


def test_load_ledger_corrupt_json_is_empty(path):
    path.write_text("{not valid json")
    assert ledger.load_ledger(path) == {"by_id": {}, "by_repo": {}}


def test_load_ledger_reads_back_a_saved_record(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", pr_ref="https://github.com/x/y/pull/1", path=path)
    loaded = ledger.load_ledger(path)
    assert loaded["by_id"]["ghostesp"]["status"] == "proposed"
    assert loaded["by_repo"]["jorgen/ghostesp"] == "ghostesp"


# ─────────────────────────── record_proposed ───────────────────────────

def test_record_proposed_writes_id_and_repo_index(path):
    ledger.record_proposed("ghostesp", "Jorgen/GhostESP", pr_ref="https://github.com/x/y/pull/1",
                           path=path, now="2026-09-01T12:00:00+00:00")

    data = json.loads(path.read_text())
    record = data["by_id"]["ghostesp"]
    assert record == {
        "id": "ghostesp", "repo": "jorgen/ghostesp", "status": "proposed",
        "timestamp": "2026-09-01T12:00:00+00:00", "pr_ref": "https://github.com/x/y/pull/1",
    }
    assert data["by_repo"]["jorgen/ghostesp"] == "ghostesp"


def test_record_proposed_pr_ref_optional(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path, now="2026-09-01T12:00:00+00:00")
    record = ledger.load_ledger(path)["by_id"]["ghostesp"]
    assert record["pr_ref"] is None


def test_record_proposed_overwrites_prior_record_for_same_id(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", pr_ref="https://x/pull/1",
                           path=path, now="2026-09-01T00:00:00+00:00")
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", pr_ref="https://x/pull/2",
                           path=path, now="2026-09-02T00:00:00+00:00")
    record = ledger.load_ledger(path)["by_id"]["ghostesp"]
    assert record["pr_ref"] == "https://x/pull/2"
    assert record["timestamp"] == "2026-09-02T00:00:00+00:00"


def test_record_proposed_uses_real_utc_now_when_not_given(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    record = ledger.load_ledger(path)["by_id"]["ghostesp"]
    assert record["timestamp"].endswith("+00:00")


# ─────────────────────────── update_status / mark_rejected ───────────────────────────

def test_update_status_transitions_an_existing_record(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path, now="2026-09-01T00:00:00+00:00")
    ledger.update_status("ghostesp", "rejected", path=path, now="2026-09-05T00:00:00+00:00")
    record = ledger.load_ledger(path)["by_id"]["ghostesp"]
    assert record["status"] == "rejected"
    assert record["timestamp"] == "2026-09-05T00:00:00+00:00"


def test_update_status_can_set_pr_ref(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    ledger.update_status("ghostesp", "merged", path=path, pr_ref="https://x/pull/9")
    assert ledger.load_ledger(path)["by_id"]["ghostesp"]["pr_ref"] == "https://x/pull/9"


def test_update_status_unknown_id_is_a_noop(path):
    result = ledger.update_status("never-proposed", "rejected", path=path)
    assert result == {"by_id": {}, "by_repo": {}}
    assert not path.exists()


def test_update_status_rejects_unknown_status_value(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    with pytest.raises(ValueError):
        ledger.update_status("ghostesp", "not-a-real-status", path=path)


def test_mark_rejected_sets_status_rejected(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    ledger.mark_rejected("ghostesp", path=path)
    assert ledger.load_ledger(path)["by_id"]["ghostesp"]["status"] == "rejected"


# ─────────────────────────── lookup / is_blocked ───────────────────────────

def test_lookup_by_id(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    data = ledger.load_ledger(path)
    assert ledger.lookup(data, firmware_id="ghostesp")["repo"] == "jorgen/ghostesp"


def test_lookup_by_repo_case_insensitive(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    data = ledger.load_ledger(path)
    assert ledger.lookup(data, repo="Jorgen/GhostESP")["id"] == "ghostesp"


def test_lookup_returns_none_when_absent(path):
    data = ledger.load_ledger(path)
    assert ledger.lookup(data, firmware_id="nope", repo="nobody/nothing") is None


def test_is_blocked_true_for_proposed(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    data = ledger.load_ledger(path)
    assert ledger.is_blocked(data, firmware_id="ghostesp") is True
    assert ledger.is_blocked(data, repo="jorgen/ghostesp") is True


def test_is_blocked_true_for_rejected(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    ledger.mark_rejected("ghostesp", path=path)
    data = ledger.load_ledger(path)
    assert ledger.is_blocked(data, firmware_id="ghostesp") is True


def test_is_blocked_false_for_merged(path):
    """Merged is deliberately NOT blocking — catalogued-in-main dedup already covers it
    (deliverable 3): the ledger must not double-gate a status the real atlas already handles."""
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    ledger.update_status("ghostesp", "merged", path=path)
    data = ledger.load_ledger(path)
    assert ledger.is_blocked(data, firmware_id="ghostesp") is False


def test_is_blocked_false_when_absent(path):
    data = ledger.load_ledger(path)
    assert ledger.is_blocked(data, firmware_id="never-seen", repo="nobody/nothing") is False


# ─────────────────────────── reconcile_merged ───────────────────────────

def test_reconcile_merged_flips_proposed_ids_now_catalogued(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    ledger.record_proposed("meshcore-cardputer", "sosprz/meshcore-cardputer", path=path)

    transitioned = ledger.reconcile_merged({"ghostesp"}, path=path, now="2026-09-10T00:00:00+00:00")

    assert transitioned == ["ghostesp"]
    data = ledger.load_ledger(path)
    assert data["by_id"]["ghostesp"]["status"] == "merged"
    assert data["by_id"]["ghostesp"]["timestamp"] == "2026-09-10T00:00:00+00:00"
    assert data["by_id"]["meshcore-cardputer"]["status"] == "proposed"


def test_reconcile_merged_leaves_already_merged_ids_untouched(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path, now="2026-09-01T00:00:00+00:00")
    ledger.update_status("ghostesp", "merged", path=path, now="2026-09-02T00:00:00+00:00")

    transitioned = ledger.reconcile_merged({"ghostesp"}, path=path, now="2026-09-10T00:00:00+00:00")

    assert transitioned == []
    assert ledger.load_ledger(path)["by_id"]["ghostesp"]["timestamp"] == "2026-09-02T00:00:00+00:00"


def test_reconcile_merged_no_write_when_nothing_transitions(path):
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    mtime_before = path.stat().st_mtime

    ledger.reconcile_merged(set(), path=path)

    assert path.stat().st_mtime == mtime_before


def test_reconcile_merged_ignores_ids_not_in_ledger(path):
    transitioned = ledger.reconcile_merged({"some-id-never-proposed"}, path=path)
    assert transitioned == []
    assert not path.exists()


# --- seeded decisions (Phase 0 PR 0.4) ------------------------------------

def test_seeded_rejections_block(path):
    """A rejected record blocks re-authoring by BOTH id and repo; a merged one does not.

    This is the shape the Phase 0 seed relies on. `BLOCKING_STATUSES` is
    ("proposed", "rejected"), so seeding a duplicate as "merged" would NOT stop the drain
    re-authoring it — the exact trap that would let BruceDevices/firmware (the renamed
    pr3y/Bruce) be authored a second time under the generic id "firmware".
    """
    ledger.record_proposed("firmware", "brucedevices/firmware", path=path)
    ledger.mark_rejected("firmware", path=path, reason="duplicate_of bruce (repo_id 795166961)")

    led = ledger.load_ledger(path)
    assert led["by_id"]["firmware"]["status"] == "rejected"
    assert ledger.is_blocked(led, firmware_id="firmware")
    # blocked by repo too: the drain's prefilter only knows the repo before it derives an id
    assert ledger.is_blocked(led, repo="brucedevices/firmware")
    assert ledger.is_blocked(led, repo="BruceDevices/firmware")  # case-insensitive


def test_merged_and_seen_do_not_block_readmission(path):
    """"merged" and "seen" are deliberately NON-blocking, so a candidate that clears the floor
    can come back through the admission gate instead of being frozen out by a stale note."""
    ledger.record_proposed("glide-synth", "charl3x/glide-synth", path=path)
    ledger.update_status("glide-synth", "seen", path=path, reason="82 stars: re-enters via the gate")
    ledger.record_proposed("ruview", "ruvnet/ruview", path=path)
    ledger.update_status("ruview", "merged", path=path)

    led = ledger.load_ledger(path)
    assert not ledger.is_blocked(led, firmware_id="glide-synth")
    assert not ledger.is_blocked(led, repo="charl3x/glide-synth")
    assert not ledger.is_blocked(led, firmware_id="ruview")


def test_reason_is_optional_and_additive(path):
    """`reason` is written only when given, and its absence is never an error — old records
    predate the field."""
    ledger.record_proposed("ghostesp", "jorgen/ghostesp", path=path)
    assert "reason" not in ledger.load_ledger(path)["by_id"]["ghostesp"]

    ledger.mark_rejected("ghostesp", path=path)
    assert "reason" not in ledger.load_ledger(path)["by_id"]["ghostesp"]

    ledger.mark_rejected("ghostesp", path=path, reason="closed unmerged by a human")
    assert ledger.load_ledger(path)["by_id"]["ghostesp"]["reason"] == "closed unmerged by a human"
