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
