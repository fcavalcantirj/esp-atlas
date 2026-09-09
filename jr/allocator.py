"""EspAtlas Jr — gauge-driven track split (jr/allocator.py).

SPEC-data-completion.md ("Jr's allocation law"): each hourly tick spends a fixed number
of track units where the finite-ground gauge says the catalog hurts most.

  - **Track A — finite backfill** (has an end): fill missing, cited board fields
    (download_mode/usb_serial First-Flash, getting-started, …). Raising these is the
    ONLY thing that moves the boards-completion gauge.
  - **Track B — infinite firmware drain** (runs forever): admit new firmware + map its
    boards as cited recipes.

The gauge (boards-completion pct) sets the split, FAVORING whichever is starved:

  - boards < 50%  → finite ground thin  → **backfill-heavy** (2/3 backfill);
  - 50–80%        → even;
  - boards > 80%  → finite covered      → **firmware-heavy** (1/3 backfill), but the
    finite floor is never zero (a new board re-opens it and the split swings back).

This inverts the pre-spec code, which was firmware-heavy while boards were thin — it
poured into the infinite ground while the finite base sat at ~1% and nothing on the
loop could raise the gauge it was optimizing.

Pure function, no I/O: allocate(boards_pct, budget_units, need_backfill=None,
need_firmware=None) → {"backfill": n, "firmware": m} with n + m == budget_units.
`need_*` are optional demand caps; a track's unused units spill to the other.

THE BANDS AND THE HOURLY UNIT BUDGET ARE PROVISIONAL — Felipe gates these (spec P5-2).
They live in exactly one place below.
"""
from __future__ import annotations

# --- provisional constants (Felipe gates these) ------------------------------------------------
BAND_BACKFILL_HEAVY_BELOW = 50.0    # boards_pct below this → backfill-heavy
BAND_FIRMWARE_HEAVY_ABOVE = 80.0    # boards_pct above this → firmware-heavy (between: even)
FAVORED_SHARE = 2 / 3               # the starved track's share in its band (even is 1/2)
HOURLY_TRACK_UNITS = 6              # track units per hourly tick

# --- demand steer (SPEC-demand-steering.md) ----------------------------------------------------
# The demand signal TILTS the base split toward the track that serves unmet UNCOVERED demand,
# but only within TILT_MAX and NEVER past the finite floor. TILT_MAX is the single source of
# truth for the steer's magnitude — jr/demand_signal.py imports it so the signal and the clamp
# agree by construction.
TILT_MAX = 0.15                     # max fraction of units the demand bias may shift either way


def _backfill_share(boards_pct: float) -> float:
    """Backfill's share of the units: 2/3 below the low band (finite thin → favor backfill),
    1/2 between, 1/3 above (finite covered → favor firmware). Monotonically NON-INCREASING
    in boards_pct — the opposite of the pre-spec code."""
    if boards_pct < BAND_BACKFILL_HEAVY_BELOW:
        return FAVORED_SHARE
    if boards_pct > BAND_FIRMWARE_HEAVY_ABOVE:
        return 1 - FAVORED_SHARE
    return 0.5


def allocate(boards_pct: float, budget_units: int, need_backfill: int | None = None,
             need_firmware: int | None = None, bias: float = 0.0) -> dict:
    """Split `budget_units` between finite backfill and the infinite firmware drain.

    The band sets the first split (backfill gets round(units * share), firmware the rest, so
    the two always sum to budget_units); then each side is capped at its demand (when given)
    and the remainder spills to the other side. A demand of 0 spills the whole share.

    `bias` (SPEC-demand-steering.md) is an OPTIONAL demand steer applied to the base split AFTER
    `_backfill_share` but BEFORE the need_* caps. It is clamped to [-TILT_MAX, TILT_MAX]
    (positive = toward firmware/Track B, negative = toward backfill/Track A) and shifts up to
    round(units * bias) units from one side to the other. `bias=0.0` (the default) is
    byte-for-byte the pre-steer behavior — full backward compatibility.

    FINITE-FLOOR CLAMP (SPEC-data-completion.md: "NEVER zero the finite floor"): while there is
    finite work (boards_pct < 100), the steer may never pull backfill below FINITE_FLOOR_SHARE =
    round(units * (share - TILT_MAX)), and never below 1 unit. The floor is capped at the base
    allocation so it only ever *restrains the steer* and never raises the gauge's base split —
    which keeps `bias=0.0` identical to today. At 100% (no finite work) the floor is released."""
    units = max(0, int(budget_units))
    share = _backfill_share(boards_pct)
    base_backfill = round(units * share)

    bias = max(-TILT_MAX, min(TILT_MAX, float(bias)))       # clamp: the steer can never exceed TILT_MAX
    shift = round(units * bias)                             # >0 toward firmware, <0 toward backfill
    backfill = max(0, min(units, base_backfill - shift))
    # finite-floor guardrail (SPEC-data-completion.md): the steer must not zero the finite floor
    if units > 0 and boards_pct < 100:
        floor = min(max(round(units * (share - TILT_MAX)), 1), base_backfill)
        backfill = max(backfill, floor)

    firmware = units - backfill
    if need_backfill is not None and backfill > need_backfill:
        firmware += backfill - need_backfill
        backfill = need_backfill
    if need_firmware is not None and firmware > need_firmware:
        backfill += firmware - need_firmware
        firmware = need_firmware
    return {"backfill": backfill, "firmware": firmware}
