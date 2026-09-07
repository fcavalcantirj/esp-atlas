"""Tests for jr/allocator.py — the gauge-driven Track A/B split. Pure function, no I/O."""
from __future__ import annotations

import allocator


def test_bands_from_the_current_gauge():
    assert allocator.allocate(42.5, 6) == {"A": 2, "B": 4}    # boards 42.5% today → B-heavy
    assert allocator.allocate(0.0, 6) == {"A": 2, "B": 4}
    assert allocator.allocate(49.9, 6) == {"A": 2, "B": 4}
    assert allocator.allocate(50.0, 6) == {"A": 3, "B": 3}    # band edges belong to even
    assert allocator.allocate(80.0, 6) == {"A": 3, "B": 3}
    assert allocator.allocate(80.1, 6) == {"A": 4, "B": 2}    # above → A-heavy
    assert allocator.allocate(100.0, 6) == {"A": 4, "B": 2}


def test_split_always_sums_to_the_budget():
    for pct in (0.0, 42.5, 50.0, 79.9, 80.1, 100.0):
        for units in (0, 1, 2, 3, 5, 6, 7, 10):
            s = allocator.allocate(pct, units)
            assert s["A"] + s["B"] == units, (pct, units, s)


def test_budget_zero_splits_nothing():
    assert allocator.allocate(42.5, 0) == {"A": 0, "B": 0}
    assert allocator.allocate(90.0, 0) == {"A": 0, "B": 0}


def test_spill_flows_unused_units_to_the_other_track():
    assert allocator.allocate(42.5, 6, need_b=1) == {"A": 5, "B": 1}   # B cannot use 3 → A
    assert allocator.allocate(90.0, 6, need_a=1) == {"A": 1, "B": 5}   # A cannot use 3 → B
    assert allocator.allocate(42.5, 6, need_b=0) == {"A": 6, "B": 0}   # zero demand spills all
    assert allocator.allocate(60.0, 6, need_a=10, need_b=10) == {"A": 3, "B": 3}  # caps above shares: no-op


def test_a_share_is_monotonic_in_boards_pct():
    for units in (1, 5, 6, 10):
        shares = [allocator.allocate(pct, units)["A"] for pct in
                  (0.0, 10.0, 42.5, 49.9, 50.0, 65.0, 80.0, 80.1, 95.0, 100.0)]
        assert shares == sorted(shares), (units, shares)
