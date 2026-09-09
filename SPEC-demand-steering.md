# SPEC — Demand-Steered Allocation (Jr's steering rule)

> **Demand TILTS the A/B split toward unmet demand — within bounds that never zero the
> finite floor. It is a bias + a report, never a gate.** (Felipe, 2026-09-09.)

This spec layers a *demand steer* on top of SPEC-data-completion.md's allocation LAW. The gauge
(finite-ground completion %) still SETS the base A:B split; demand only nudges it. The finite
floor from SPEC-data-completion.md ("**NEVER zero the finite floor**") is preserved verbatim —
the steer can never override it.

## The steering rule

- **UNCOVERED demand = Jr's authoring signal.** Only `UNCOVERED` items feed the steer. They name
  a specific catalog gap a real search/first-party query is asking for and Jr can author toward.
- **`RANKS_POORLY` is a human SEO/content report, NEVER an authoring or allocation trigger.** It
  means a page that already exists ranks badly — a content/SEO fix for a person, not something Jr
  writes. It is surfaced in the report under its own clearly-labelled section and is EXCLUDED from
  every steering bucket. (This matches `demand.py`'s digest: "RANKS_POORLY — report for Felipe+us,
  never Jr's authoring path".)
- **`COVERED_OK` / `UNRESOLVED` are informational.** Covered demand needs nothing; unresolved
  demand is a review list for Felipe (possible new categories), never an authoring target.

### Which track a piece of UNCOVERED demand tilts toward
- An UNCOVERED item whose `resolved` carries a `firmware_token` **or** a `board`+`firmware_token`
  pairing → **firmware/recipe demand → biases toward Track B (firmware)**.
- An UNCOVERED item resolving to a `part` / `chip` / `board` with **no firmware angle** (no
  `firmware_token`) → **finite/board demand → biases toward Track A (backfill)**.

## The bias

`steer_signal(snapshot)` derives a single signed tilt:

- `bias ∈ [-TILT_MAX, +TILT_MAX]` (TILT_MAX = 0.15). **Positive = toward firmware (Track B);
  negative = toward backfill (Track A).**
- The magnitude is the *relative weight* of the two UNCOVERED demand pools:

  ```
  fw   = Σ weight of uncovered_firmware items
  fin  = Σ weight of uncovered_finite items
  bias = TILT_MAX * (fw - fin) / (fw + fin)          when (fw + fin) > 0
       = 0.0                                          otherwise
  ```

- **Zero when there is no UNCOVERED demand** (nothing to steer toward). `RANKS_POORLY`,
  `COVERED_OK` and `UNRESOLVED` items contribute nothing to `fw`/`fin`, so a snapshot with no
  UNCOVERED items always yields `bias == 0.0`.

## The finite-floor guardrail (allocator)

`allocator.allocate(..., bias: float = 0.0)` applies the bias to the base split AFTER
`_backfill_share` sets it but BEFORE the `need_*` caps:

1. Base split: `backfill = round(units * share)`, `firmware = units - backfill`.
2. Shift up to `round(units * bias)` units from one side to the other:
   - `bias > 0` → move units backfill → firmware (toward Track B);
   - `bias < 0` → move units firmware → backfill (toward Track A).
3. **CLAMP (SPEC-data-completion.md — "NEVER zero the finite floor"):** when `boards_pct < 100`
   there is finite work, so backfill is never allowed below
   `FINITE_FLOOR_SHARE = round(units * (share - TILT_MAX))` and never below **1 unit**. The steer
   can lean the split but can never starve the finite ground while it is incomplete.
4. Then apply `need_backfill` / `need_firmware` caps exactly as today (spill the remainder).

`bias = 0.0` is byte-for-byte the current behavior — every existing allocator test passes
unchanged. Backward compatible: `bias` is an optional trailing keyword.

## The stale / missing fallback

Demand steering is best-effort and never a gate:

- **Missing snapshot** (`docs/demand/<date>.json` absent) → `load_latest` returns `None` → NO
  steer: `bias = 0.0`, the allocator behaves exactly as SPEC-data-completion.md defines today.
- **Stale snapshot** → the latest snapshot's `date` is older than `stale_days` (default **14**)
  relative to `today_str`. When stale: `stale = True`, NO steer (`bias = 0.0`), and the report
  says so ("demand snapshot stale (age Nd) — not steering").
- The tick READS the committed `docs/demand/<date>.json` only; it never runs `demand.py` (which
  needs the composio venv the tick lacks). A load/parse failure is caught, warned, and treated
  as "no steer".

## The alignment report

`alignment(snapshot, supply_row)` is a deterministic supply×demand report (no clock, no I/O):

- **`aligned_pct`** = share of total demand **weight** that is `COVERED_OK`, i.e.
  `Σ weight(COVERED_OK) / Σ weight(all items)` (×100, rounded). 0 when there is no weight.
- **counts per gap class** (`UNCOVERED` / `RANKS_POORLY` / `COVERED_OK` / `UNRESOLVED`).
- **`demanded_but_missing`** — the worklist: `UNCOVERED` first, then `RANKS_POORLY`, ranked by
  weight, top N. UNCOVERED items are Jr's authoring path; RANKS_POORLY ride along labelled as the
  human SEO list.

The tick renders, in the PR body:
- the data line extended with `· demand: aligned XX% · N uncovered` when a fresh snapshot exists;
- a `### Demand alignment` section: the top demanded-but-missing UNCOVERED items (Jr's worklist)
  and a separate, clearly-labelled `RANKS_POORLY (SEO — human)` mini-list that is explicitly NOT
  Jr's authoring path;
- when stale/missing, ONE honest line instead of the section.

## Invariants (tested)
1. `bias = 0.0` ⇒ allocator identical to today (all pre-existing cases).
2. A positive bias shifts toward firmware but backfill never drops below the finite floor.
3. Bias never zeroes backfill when finite work remains (`boards_pct < 100`).
4. `RANKS_POORLY` never enters an authoring/steer bucket; only `UNCOVERED` does.
5. No UNCOVERED demand ⇒ `bias == 0.0`; otherwise `bias ∈ [-TILT_MAX, TILT_MAX]`.
6. Missing/stale snapshot ⇒ `bias == 0.0` and an honest report line.
