"""Tests for jr/budget.py — the tick's call/time counter. A fake clock drives every time assertion."""
from __future__ import annotations

import pytest

import budget as b


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def test_charge_counts_and_stops_before_crossing_the_cap():
    bud = b.Budget(max_calls=3, max_seconds=60, clock=Clock())
    bud.charge(); bud.charge()
    assert bud.calls == 2 and bud.remaining_calls() == 1 and not bud.exhausted()
    bud.charge()
    assert bud.exhausted()
    with pytest.raises(b.BudgetExceeded) as e:
        bud.charge()
    assert "call budget" in str(e.value)
    assert bud.calls == 3                      # the refused charge was not spent


def test_time_cap_refuses_once_elapsed():
    clk = Clock(100.0)
    bud = b.Budget(max_calls=10, max_seconds=30, clock=clk)
    clk.t = 129.0
    bud.charge()
    clk.t = 130.0
    assert bud.remaining_seconds() == 0.0 and bud.exhausted()
    with pytest.raises(b.BudgetExceeded) as e:
        bud.charge()
    assert "time budget" in str(e.value)


def test_wrap_charges_one_per_call_and_delegates():
    calls = []
    bud = b.Budget(max_calls=2, clock=Clock())
    gh = bud.wrap(lambda *a: calls.append(a) or "ok")
    assert gh("api", "x") == "ok" and gh("pr", "list") == "ok"
    assert calls == [("api", "x"), ("pr", "list")] and bud.calls == 2
    with pytest.raises(b.BudgetExceeded):
        gh("api", "y")
    assert len(calls) == 2                     # the third call never reached gh


def test_summary_is_one_readable_fragment():
    clk = Clock(5.0)
    bud = b.Budget(max_calls=150, max_seconds=360, clock=clk)
    bud.charge(7)
    clk.t = 17.5
    assert bud.summary() == "gh calls 7/150 · 12.5s/360s"


def test_defaults_match_the_plan():
    bud = b.Budget(clock=Clock())
    assert bud.max_calls == 150 and bud.max_seconds == 360.0
