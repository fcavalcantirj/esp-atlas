"""EspAtlas Jr — gauge-driven Track A/B split (jr/allocator.py).

Phase 5: the hourly tick cannot do everything, so each tick spends a fixed number of track
units where the gauge says the catalog hurts most. Boards completion (scripts/data_completion
boards pct) drives the split:

  - boards < 50% → B-heavy (map what the repos declare; the catalog is thin on boards);
  - 50–80%      → even;
  - boards > 80% → A-heavy (boards are covered; admit new firmware).

Pure function, no I/O: allocate(boards_pct, budget_units, need_a=None, need_b=None) takes
the gauge and the tick's track-unit budget and returns {"A": n, "B": m} with n + m ==
budget_units. `need_a`/`need_b` are optional demand caps: units a track cannot use spill
to the other (uncapped when None).

THE BANDS AND THE HOURLY UNIT BUDGET ARE PROVISIONAL — Felipe's yes is required before
merge (spec P5-2). They were proposed from the gauge at write time (boards 42.5%: B-heavy
country) and live in exactly one place below.
"""
from __future__ import annotations

# --- provisional constants (Felipe gates these) ------------------------------------------------
BAND_B_HEAVY_BELOW = 50.0    # boards_pct below this → B-heavy
BAND_A_HEAVY_ABOVE = 80.0    # boards_pct above this → A-heavy (between: even)
SHARE_A_B_HEAVY = 1 / 3      # A-heavy mirrors it (2/3); even is 1/2
HOURLY_TRACK_UNITS = 6       # track units per hourly tick (the old plan's C = 6 default)


def _band_share(boards_pct: float) -> float:
    """A's share of the units: 1/3 below the low band, 1/2 between, 2/3 above."""
    if boards_pct < BAND_B_HEAVY_BELOW:
        return SHARE_A_B_HEAVY
    if boards_pct > BAND_A_HEAVY_ABOVE:
        return 1 - SHARE_A_B_HEAVY
    return 0.5


def allocate(boards_pct: float, budget_units: int, need_a: int | None = None,
             need_b: int | None = None) -> dict:
    """Split `budget_units` track units between admission (A) and board-mapping (B).

    The band sets the first split (A gets round(units * share), B the rest, so the two
    always sum to budget_units); then each side is capped at its demand (when given) and
    the remainder spills to the other side. A demand of 0 spills the whole share."""
    units = max(0, int(budget_units))
    a = round(units * _band_share(boards_pct))
    b = units - a
    if need_a is not None and a > need_a:
        b += a - need_a
        a = need_a
    if need_b is not None and b > need_b:
        a += b - need_b
        b = need_b
    return {"A": a, "B": b}
