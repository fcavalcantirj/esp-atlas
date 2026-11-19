"""Tests for jr/allocator.py — the gauge-driven backfill/firmware split (SPEC-data-completion.md).
Pure function, no I/O. Finite ground thin → favor backfill; covered → favor firmware."""
from __future__ import annotations

import allocator


def test_bands_favor_backfill_when_finite_is_thin():
    assert allocator.allocate(42.5, 6) == {"backfill": 4, "firmware": 2}   # boards 42.5% today → backfill-heavy
    assert allocator.allocate(0.0, 6) == {"backfill": 4, "firmware": 2}
    assert allocator.allocate(49.9, 6) == {"backfill": 4, "firmware": 2}
    assert allocator.allocate(50.0, 6) == {"backfill": 3, "firmware": 3}   # band edges belong to even
    assert allocator.allocate(80.0, 6) == {"backfill": 3, "firmware": 3}
    assert allocator.allocate(80.1, 6) == {"backfill": 2, "firmware": 4}   # covered → firmware-heavy
    assert allocator.allocate(100.0, 6) == {"backfill": 2, "firmware": 4}


def test_split_always_sums_to_the_budget():
    for pct in (0.0, 42.5, 50.0, 79.9, 80.1, 100.0):
        for units in (0, 1, 2, 3, 5, 6, 7, 10):
            s = allocator.allocate(pct, units)
            assert s["backfill"] + s["firmware"] == units, (pct, units, s)


def test_budget_zero_splits_nothing():
    assert allocator.allocate(42.5, 0) == {"backfill": 0, "firmware": 0}
    assert allocator.allocate(90.0, 0) == {"backfill": 0, "firmware": 0}


def test_spill_flows_unused_units_to_the_other_track():
    assert allocator.allocate(42.5, 6, need_firmware=1) == {"backfill": 5, "firmware": 1}   # firmware can't use 2 → backfill
    assert allocator.allocate(90.0, 6, need_backfill=1) == {"backfill": 1, "firmware": 5}   # backfill can't use 2 → firmware
    assert allocator.allocate(42.5, 6, need_firmware=0) == {"backfill": 6, "firmware": 0}    # zero demand spills all
    assert allocator.allocate(60.0, 6, need_backfill=10, need_firmware=10) == {"backfill": 3, "firmware": 3}  # caps above shares: no-op


def test_backfill_share_is_monotonic_non_increasing_in_boards_pct():
    # the finite floor: as boards fill, backfill's share only ever DROPS (opposite of pre-spec)
    for units in (1, 5, 6, 10):
        shares = [allocator.allocate(pct, units)["backfill"] for pct in
                  (0.0, 10.0, 42.5, 49.9, 50.0, 65.0, 80.0, 80.1, 95.0, 100.0)]
        assert shares == sorted(shares, reverse=True), (units, shares)


# --- demand steer (SPEC-demand-steering.md): an OPTIONAL bias tilts the base split -------------

def test_bias_zero_is_byte_for_byte_the_pre_spec_behavior():
    # the whole backward-compat contract: bias defaulting to 0.0 must not change any split
    for pct in (0.0, 10.0, 42.5, 49.9, 50.0, 65.0, 80.0, 80.1, 95.0, 100.0):
        for units in (0, 1, 2, 3, 5, 6, 7, 10):
            base = allocator.allocate(pct, units)
            assert allocator.allocate(pct, units, bias=0.0) == base, (pct, units)
            # caps also unchanged under bias=0.0
            assert allocator.allocate(pct, units, need_firmware=1, bias=0.0) == \
                allocator.allocate(pct, units, need_firmware=1), (pct, units)


def test_positive_bias_shifts_toward_firmware_but_never_zeroes_the_finite_floor():
    # boards 42.5% → base backfill-heavy {4,2}; a +TILT_MAX bias moves one unit to firmware
    steered = allocator.allocate(42.5, 6, bias=0.15)
    assert steered == {"backfill": 3, "firmware": 3}
    assert steered["backfill"] + steered["firmware"] == 6
    # the shift is toward firmware vs the unbiased base
    assert steered["firmware"] > allocator.allocate(42.5, 6)["firmware"]


def test_negative_bias_shifts_toward_backfill():
    steered = allocator.allocate(42.5, 6, bias=-0.15)
    assert steered == {"backfill": 5, "firmware": 1}
    assert steered["backfill"] > allocator.allocate(42.5, 6)["backfill"]


def test_bias_never_zeroes_backfill_while_finite_work_remains():
    # even at boards 90% (firmware-heavy base) an aggressive firmware tilt keeps a floor
    for bias in (0.15, 0.5, 1.0):        # over-range bias is clamped, floor still holds
        s = allocator.allocate(90.0, 6, bias=bias)
        assert s["backfill"] >= 1, (bias, s)
        assert s["backfill"] + s["firmware"] == 6
    # the finite floor BINDS here: boards 90%, 4 units, base backfill 1; a +bias shift of 1 would
    # zero it — the guardrail clamps it back to 1 (SPEC-data-completion.md: never zero the floor)
    assert allocator.allocate(90.0, 4, bias=0.15)["backfill"] == 1
    # at 100% (no finite work) the floor is released — the same shift may reach 0
    assert allocator.allocate(100.0, 4, bias=0.15)["backfill"] == 0


def test_bias_is_clamped_to_tilt_max():
    # an out-of-range bias behaves exactly like the saturated TILT_MAX bias
    assert allocator.allocate(42.5, 6, bias=9.0) == allocator.allocate(42.5, 6, bias=allocator.TILT_MAX)
    assert allocator.allocate(42.5, 6, bias=-9.0) == allocator.allocate(42.5, 6, bias=-allocator.TILT_MAX)


def test_bias_still_sums_to_budget_and_respects_need_caps():
    for pct in (0.0, 42.5, 65.0, 90.0, 100.0):
        for units in (0, 1, 3, 6, 10):
            for bias in (-0.15, 0.0, 0.07, 0.15):
                s = allocator.allocate(pct, units, bias=bias)
                assert s["backfill"] + s["firmware"] == units, (pct, units, bias, s)
    # need caps applied AFTER the bias still spill correctly
    assert allocator.allocate(42.5, 6, need_firmware=1, bias=0.15) == {"backfill": 5, "firmware": 1}


# --- the yield rule (SPEC-data-completion.md "Yield", 2026-11-17) -----------------------------------------

def _y(backfill=(24, 72, 0), firmware=(24, 72, 3)):
    """(ticks, units, produced) per lane, the shape jr/yield_ledger.lane_yield returns."""
    return {"backfill": dict(zip(("ticks", "units", "produced"), backfill)),
            "firmware": dict(zip(("ticks", "units", "produced"), firmware)), "window_ticks": 24, "ticks_in_window": 24}


def test_a_lane_dead_over_a_full_window_keeps_only_the_floor_and_the_producer_gets_the_rest():
    # measured Nov 10-17: backfill 0 produced in 160/160 ticks on 3 units an hour; firmware produced
    assert allocator.allocate(61.7, 6, yields=_y()) == {"backfill": 1, "firmware": 5}
    assert allocator.allocate(61.7, 6, yields=_y(backfill=(24, 72, 4), firmware=(24, 72, 0))) == {"backfill": 5, "firmware": 1}
    assert allocator.yield_caps(_y(), 24)["dead"] == ["backfill"]


def test_both_lanes_silent_is_a_stall_not_a_tilt():
    assert allocator.allocate(61.7, 6, yields=_y(backfill=(24, 72, 0), firmware=(24, 72, 0))) == {"backfill": 3, "firmware": 3}
    assert allocator.yield_caps(_y(backfill=(24, 72, 0), firmware=(24, 72, 0)), 24) == {"need_backfill": None, "need_firmware": None, "dead": []}


def test_a_window_not_yet_full_never_moves_units():
    assert allocator.allocate(61.7, 6, yields=_y(backfill=(23, 69, 0))) == {"backfill": 3, "firmware": 3}
    assert allocator.allocate(61.7, 6, yields=_y(backfill=(0, 0, 0))) == {"backfill": 3, "firmware": 3}   # a parked lane is not dead


def test_the_floor_is_configurable_and_the_split_still_sums():
    assert allocator.allocate(61.7, 6, yields=_y(), floor_units=2) == {"backfill": 2, "firmware": 4}
    for units in (1, 2, 5, 6, 7):
        s = allocator.allocate(42.5, units, yields=_y())
        assert s["backfill"] + s["firmware"] == units


def test_explicit_need_caps_and_the_yield_cap_compose_as_a_min():
    assert allocator.allocate(61.7, 6, yields=_y(), need_backfill=0) == {"backfill": 0, "firmware": 6}
    assert allocator.allocate(61.7, 6, yields=_y(), need_backfill=2) == {"backfill": 1, "firmware": 5}


def test_no_yields_is_byte_for_byte_the_previous_behaviour():
    for pct in (0.0, 42.5, 61.7, 80.1, 100.0):
        assert allocator.allocate(pct, 6, yields=None) == allocator.allocate(pct, 6)
        assert allocator.allocate(pct, 6, yields={}) == allocator.allocate(pct, 6)
