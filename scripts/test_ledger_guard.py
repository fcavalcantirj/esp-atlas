"""Tests for scripts/ledger_guard.py — pure checks over two ledgers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger_guard as lg  # noqa: E402


def _rec(k, status, **kw):
    return {"id": k, "repo": f"o/{k}", "status": status, **kw}


def test_appending_dated_rejections_and_reconciling_a_proposal_to_merged_is_fine():
    base = {"by_id": {"a": _rec("a", "proposed"), "m": _rec("m", "merged")}}
    head = {"by_id": {"a": _rec("a", "merged"), "m": _rec("m", "merged"),
                      "x": _rec("x", "rejected", expires="2026-10-07"), "y": _rec("y", "seen", expires="2026-10-07")}}
    assert lg.check(base, head) == []


def test_tick_153_shape_is_refused_merged_and_proposed_downgraded_by_ttl_rejections():
    base = {"by_id": {"esp-claw": _rec("esp-claw", "merged"), "taskhub": _rec("taskhub", "proposed")}}
    head = {"by_id": {"esp-claw": _rec("esp-claw", "rejected", expires="2026-10-07"),
                      "taskhub": _rec("taskhub", "rejected", expires="2026-10-07")}}
    out = lg.check(base, head)
    assert any(m.startswith("'esp-claw': merged -> rejected") for m in out)
    assert any(m.startswith("'taskhub': proposed -> rejected") for m in out)


def test_a_permanent_rejection_the_human_veto_may_follow_merged_or_proposed():
    base = {"by_id": {"m": _rec("m", "merged"), "p": _rec("p", "proposed")}}
    head = {"by_id": {"m": _rec("m", "rejected", reason="removed by a human"), "p": _rec("p", "rejected", reason="PR closed")}}
    assert lg.check(base, head) == []


def test_removed_records_undated_notes_and_key_mismatches_are_refused():
    base = {"by_id": {"a": _rec("a", "merged")}}
    head = {"by_id": {"b": _rec("b", "seen"), "c": {"id": "zzz", "status": "rejected", "expires": "2026-10-07"}, "": _rec("", "rejected")}}
    out = lg.check(base, head)
    assert any("record removed: 'a'" in m for m in out)
    assert any("'b': seen without expires" in m for m in out)
    assert any("'c': id field 'zzz'" in m for m in out)
    assert any("bad key ''" in m for m in out)


def test_main_against_the_real_repo_is_green_for_an_unchanged_ledger():
    assert lg.main(["--base", "HEAD"]) == 0
