"""EspAtlas Jr — pytest for the demand STEER + alignment (jr/demand_signal.py,
SPEC-demand-steering.md). Every test runs OFFLINE over hand-built snapshots shaped exactly
like `docs/demand/<date>.json` (real esp32-domain terms/ids). No network, no clock except the
injected `today_str`.

The crux under test: only UNCOVERED demand steers (RANKS_POORLY is a human SEO report, never an
authoring/allocation trigger); the bias is bounded by TILT_MAX and zero with no UNCOVERED
demand; the alignment score is deterministic weight math.

Run: cd jr && python3 -m pytest test_demand_signal.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demand_signal  # noqa: E402


# --- fixture builders (docs/demand/<date>.json shape) ------------------------------------------

def _item(term, gap, weight, resolved, impressions=None, ctr=None, position=None):
    return {"term": term, "gap": gap, "weight": weight, "impressions": impressions,
            "ctr": ctr, "position": position, "resolved": resolved}


def _fw(token, board=None):
    return {"board": board, "chip": None, "firmware_token": token, "capability": [], "part": None}


def _part(part, chip=None):
    return {"board": None, "chip": chip, "firmware_token": None, "capability": [], "part": part}


def _snap(date, items):
    return {"date": date, "window": {"start": "x", "end": date}, "weight_formula_version": "v1",
            "d2_available": False, "count": len(items), "items": items}


# a realistic mixed snapshot: an UNCOVERED firmware gap, an UNCOVERED finite/part gap, a
# RANKS_POORLY SEO row (must NEVER steer), plus COVERED_OK/UNRESOLVED noise.
MIXED = _snap("2026-09-09", [
    _item("esp32-c6", "RANKS_POORLY", 421.59, _part("esp32-c6", "esp32-c6"), impressions=134, ctr=0.0075, position=31.7),
    _item("m5stack stick s3", "UNCOVERED", 27.0, _fw("m5stack-avatar-mic", "m5stick-s3"), impressions=11),
    _item("bruce esp32 flipper", "UNCOVERED", 18.0, _fw("bruce-flipper"), impressions=14),
    _item("esp32-c9", "UNCOVERED", 10.0, _part("esp32-c9", "esp32-c9"), impressions=12),
    _item("launcher esp32", "COVERED_OK", 76.68, _fw("launcher"), impressions=115),
    _item("m5 stick s3", "UNRESOLVED", 13.75, {"board": "m5stick-s3", "chip": "esp32-s3",
          "firmware_token": None, "capability": [], "part": None}, impressions=11),
])


# --- load_latest -------------------------------------------------------------------------------

def _write(dirp, snap):
    (dirp / f"{snap['date']}.json").write_text(json.dumps(snap))


def test_load_latest_picks_the_newest_and_ignores_unresolved(tmp_path):
    _write(tmp_path, _snap("2026-08-31", []))
    _write(tmp_path, _snap("2026-09-09", MIXED["items"]))
    (tmp_path / "unresolved.json").write_text(json.dumps({"count": 0, "items": []}))
    got = demand_signal.load_latest(tmp_path, "2026-09-09")
    assert got is not None and got["date"] == "2026-09-09"
    assert got["age_days"] == 0 and got["stale"] is False
    assert len(got["items"]) == len(MIXED["items"])       # newest snapshot's content, not the older one


def test_load_latest_flags_stale_past_the_threshold(tmp_path):
    _write(tmp_path, _snap("2026-09-09", []))
    fresh = demand_signal.load_latest(tmp_path, "2026-09-20")          # 11 days < 14 default
    assert fresh is not None and fresh["age_days"] == 11 and fresh["stale"] is False
    stale = demand_signal.load_latest(tmp_path, "2026-09-24")          # 15 days > 14 default
    assert stale is not None and stale["age_days"] == 15 and stale["stale"] is True
    tight = demand_signal.load_latest(tmp_path, "2026-09-15", stale_days=3)   # 6 days > 3
    assert tight["stale"] is True


def test_load_latest_returns_none_when_no_snapshot(tmp_path):
    assert demand_signal.load_latest(tmp_path, "2026-09-09") is None
    assert demand_signal.load_latest(tmp_path / "missing", "2026-09-09") is None
    (tmp_path / "unresolved.json").write_text("{}")
    assert demand_signal.load_latest(tmp_path, "2026-09-09") is None   # unresolved alone is not a snapshot


# --- steer_signal: bucketing -------------------------------------------------------------------

def test_steer_signal_buckets_uncovered_firmware_vs_finite_and_excludes_ranks_poorly():
    sig = demand_signal.steer_signal(MIXED)
    fw_terms = [it["term"] for it in sig["uncovered_firmware"]]
    fin_terms = [it["term"] for it in sig["uncovered_finite"]]
    # firmware_token (or board+firmware pairing) → firmware; part/chip/board only → finite
    assert fw_terms == ["m5stack stick s3", "bruce esp32 flipper"]     # ranked by weight desc
    assert fin_terms == ["esp32-c9"]
    # RANKS_POORLY is a human SEO report — NEVER an authoring/steer bucket
    all_steer_terms = fw_terms + fin_terms
    assert "esp32-c6" not in all_steer_terms
    # COVERED_OK / UNRESOLVED are informational, not steer buckets either
    assert "launcher esp32" not in all_steer_terms and "m5 stick s3" not in all_steer_terms
    # the SEO section carries RANKS_POORLY, ranked by impressions
    assert [it["term"] for it in sig["ranks_poorly"]] == ["esp32-c6"]


def test_ranks_poorly_ranked_by_impressions():
    snap = _snap("2026-09-09", [
        _item("esp32 h2", "RANKS_POORLY", 165.5, _part("esp32-h2"), impressions=50),
        _item("esp32-c6", "RANKS_POORLY", 421.59, _part("esp32-c6"), impressions=134),
    ])
    sig = demand_signal.steer_signal(snap)
    assert [it["term"] for it in sig["ranks_poorly"]] == ["esp32-c6", "esp32 h2"]   # 134 > 50


# --- steer_signal: bias ------------------------------------------------------------------------

def test_bias_is_zero_with_no_uncovered_demand():
    snap = _snap("2026-09-09", [
        _item("esp32-c6", "RANKS_POORLY", 999.0, _part("esp32-c6"), impressions=134),
        _item("launcher esp32", "COVERED_OK", 76.68, _fw("launcher"), impressions=115),
        _item("m5 stick s3", "UNRESOLVED", 13.75, _part(None), impressions=11),
    ])
    sig = demand_signal.steer_signal(snap)
    assert sig["bias"] == 0.0
    assert sig["uncovered_firmware"] == [] and sig["uncovered_finite"] == []


def test_bias_is_positive_toward_firmware_and_within_bounds():
    sig = demand_signal.steer_signal(MIXED)
    # fw weight = 27+18 = 45, fin weight = 10 → positive (toward firmware), bounded by TILT_MAX
    assert 0.0 < sig["bias"] <= demand_signal.TILT_MAX
    expected = round(demand_signal.TILT_MAX * (45.0 - 10.0) / (45.0 + 10.0), 4)
    assert sig["bias"] == expected


def test_bias_saturates_to_minus_tilt_max_when_only_finite_demand():
    snap = _snap("2026-09-09", [
        _item("esp32-c9", "UNCOVERED", 10.0, _part("esp32-c9")),
        _item("esp32-c5", "UNCOVERED", 5.0, _part("esp32-c5")),
    ])
    sig = demand_signal.steer_signal(snap)
    assert sig["bias"] == -demand_signal.TILT_MAX          # all finite → full tilt toward backfill


def test_bias_saturates_to_plus_tilt_max_when_only_firmware_demand():
    snap = _snap("2026-09-09", [_item("bruce esp32", "UNCOVERED", 12.0, _fw("bruce-x"))])
    sig = demand_signal.steer_signal(snap)
    assert sig["bias"] == demand_signal.TILT_MAX


# --- alignment ---------------------------------------------------------------------------------

def test_alignment_score_is_covered_weight_share_with_counts_and_worklist():
    align = demand_signal.alignment(MIXED, supply_row={"finite_overall_pct": 41.2, "firmware_count": 30})
    total = 421.59 + 27.0 + 18.0 + 10.0 + 76.68 + 13.75
    assert align["aligned_pct"] == round(76.68 / total * 100)          # only COVERED_OK weight counts as aligned
    assert align["counts"] == {"UNCOVERED": 3, "RANKS_POORLY": 1, "COVERED_OK": 1, "UNRESOLVED": 1}
    assert align["uncovered"] == 3
    # demanded_but_missing: UNCOVERED first (Jr worklist), then RANKS_POORLY, each ranked by weight
    dbm = [(it["term"], it["gap"]) for it in align["demanded_but_missing"]]
    assert dbm == [("m5stack stick s3", "UNCOVERED"), ("bruce esp32 flipper", "UNCOVERED"),
                   ("esp32-c9", "UNCOVERED"), ("esp32-c6", "RANKS_POORLY")]


def test_alignment_top_n_caps_the_worklist():
    items = [_item(f"gap-{i}", "UNCOVERED", float(i), _part(f"esp32-x{i}")) for i in range(20)]
    align = demand_signal.alignment(_snap("2026-09-09", items), supply_row=None, top_n=5)
    assert len(align["demanded_but_missing"]) == 5
    assert [it["term"] for it in align["demanded_but_missing"]] == [f"gap-{i}" for i in (19, 18, 17, 16, 15)]


def test_alignment_handles_zero_weight_without_dividing_by_zero():
    align = demand_signal.alignment(_snap("2026-09-09", []), supply_row=None)
    assert align["aligned_pct"] == 0 and align["counts"]["UNCOVERED"] == 0
    assert align["demanded_but_missing"] == []
