# SPEC — Data Completion Priority (Jr's allocation law)

> **Cover the FINITE foundation before chasing INFINITE ground.** Basic needs covered
> before infinite ground. (Felipe, 2026-09-01.)

## Finite vs infinite
- **Finite ground (bounded — must be *completed*):** socs, modules, **boards**, brands, and
  their docs — pinouts, `download_mode`/`usb_serial` (First-Flash), getting-started /
  annotated board diagram, datasheet-cited specs. There is a *knowable, finite* set of ESP32
  dev boards and parts. This can reach 100%.
- **Infinite ground (unbounded — never "done"):** firmware, recipes, examples. The community
  makes more forever; there is no 100%.

## The allocation rule
Each Jr run allocates effort by the **finite-ground completion gauge**:
- **Finite ground has gaps → SPLIT effort, favoring the finite backfill** (missing board
  fields, missing boards/parts, docs) over new firmware.
- **Finite ground "complete" → most effort to new firmware/discovery, but NEVER zero on finite.**
  "Complete" is a *moment, not forever*: **manufacturers keep shipping new boards/parts** (C5,
  P4, C61…), so a thin **manufacturer-watch always runs**. When it finds a new board/part, the
  finite ground re-opens and the split swings back toward Track A until it's covered again.

The split favors whichever is more starved; the finite part is the floor — basics covered
before pouring into the infinite — but the floor is a moving target, never permanently closed.

## Yield: the split answers to what the lanes actually produce (2026-11-17)

Measured over the 160 tick PRs of 2026-11-10 → 11-17 before this rule existed: backfill produced **0 in
160/160 ticks** on 3 units an hour (480 units spent on a lane whose worklist was 84/119 boards cooling);
firmware (admit + boardmap) produced in 24/160 ticks with normal gaps of 1–4 ticks; one zero streak of 51
ticks (Nov 15 21Z → Nov 17 23Z) passed with the split unchanged at 3/3 and no alarm. The gauge alone cannot
see that: it says how thin the ground is, not whether the lane digging it moves anything.

- **The yield ledger** (`jr/yield_ledger.py`, `docs/telemetry/yield.jsonl`, an AUTO bookkeeping path): every
  hourly tick appends one row per content stage — `tick`, `stage`, `units` it received, `produced` (filled
  fields, admitted records, written recipes), the stage's own `counts`, and the tick's `calls`/`seconds`.
  Idempotent per (tick, stage); a corrupt line is skipped.
- **Lanes**: backfill = Track A; firmware = admit + boardmap (Track B); topics is tracked but stays outside
  the split. Yield per lane is summed over the trailing `window_ticks` distinct ticks BEFORE the current one,
  counting only ticks in which the lane had units (a lane parked at zero units is never "dead").
- **The rule** (`jr/allocator.allocate(..., yields=, window_ticks=, floor_units=)`): a split lane observed over
  a FULL window that produced nothing while the other produced keeps only `floor_units`; its spare units
  spill to the producer through the same `need_*` caps the demand steer uses, after the band split, the
  bias and the finite-floor clamp. Both lanes silent → the split stands and the tick reports a **stall**
  (`stall_ticks`; the incident is SPEC-jr-self-heal.md's). A window not yet full moves nothing. No
  `yields` → byte-for-byte the previous behaviour.
- **The constants live in `jr/steering.json`** (`hourly_units`, `yield.window_ticks` 24, `yield.floor_units`
  1, `yield.stall_ticks` 24, `yield.topics_stall_ticks` 48, `delegate_runs_per_day` 2), read at tick start by
  `jr/steering.py`; a missing or invalid value falls back to the same default alone and the tick says so.
  The bands above stay in `jr/allocator.py` until a reviewed PR moves them too.
- **Every tick prints its inputs**: `boards 61.7% -> backfill 1 / firmware 5 (hourly) · yield backfill 0/72u
  firmware 3/72u topics 0/48u (24 ticks) → backfill at floor`.

Acceptance: `jr/test_allocator.py` (yield rule), `jr/test_yield_ledger.py`, `jr/test_steering.py`,
`jr/test_tick_dry_run.py` (the ledger rides the real tick; the dry run lists it). Live: the first 24 ticks
after merge write 24 × 4 rows; the 25th tick prints the yield text and, with backfill still at 0, runs
`backfill 1 / firmware 5`.

## Discovery is multi-source (not just the launcher catalog)
Jr finds new work from several signals, feeding BOTH tracks — this matches JR.md's *Discover*
columns (manufacturer watch + community), which the current launcher-only drain doesn't yet
implement:
- **Launcher / M5Burner catalog + GitHub popularity** (downloads × stars) — the current drain.
- **Manufacturer watch** — Espressif + third-party vendors' new board/part releases → **Track A**
  (perpetual; keeps the finite ground current).
- **Community signal** — thriving posts on **r/esp32**, Hacker News, maker blogs → surfaces hot
  new *firmware* AND new *boards/projects* the catalog + manufacturer-watch miss → **both tracks**.

## What counts as "complete" (per finite entity)
Baseline = schema-`required` fields (the guard already enforces these → always 100%). The gauge
measures the **usefulness fields** *beyond* baseline that make a record actually useful, each of
which must be **cited** (cite-or-omit) to count:
- **board (the priority):** `download_mode`, `usb_serial`, `io.gpio_pins` (pinout),
  `dimensions_mm`, `form_factor`, `usb.connector`, and a getting-started link / board-diagram
  (field to add).
- **soc / module:** the datasheet-cited key specs per its schema (cpu cores/freq, ram, flash,
  wifi/ble/radio, gpio count, native-usb); module adds flash / psram / antenna / certs.
- **brand:** homepage present + liveness-verified.

Overall finite-completion % = mean of per-entity completion, **weighted so boards dominate**
(they're what First-Flash needs).

## The data completion gauge (to build)
A single report over the FINITE entities — per entity type and per required field, the % of
records complete (cited):
- **boards:** % with `download_mode`, `usb_serial`, pinout (`io`), getting-started/diagram,
  dimensions, …
- **socs / modules:** % with datasheet-cited required fields.
- **Overall finite-completion %** — the number that drives the allocation above.

Surfaced as `npm run data:completion` (evolve `boot:coverage` into the full gauge), and folded
into the Jr telemetry + the public `/status` page.

## Jr becomes two-track
- **Track A — finite backfill (has an end):** fill gaps in the finite ground — boot data,
  pinouts, missing boards/parts, getting-started — each cite-or-omit. Feeds off the gauge's
  worklist.
- **Track B — infinite firmware drain (runs forever):** the launcher drain — GitHub popularity
  (dominant) + *slight* demand steer (GSC/first-party) + `seen`-coverage so it always advances.
- The **completion gauge sets the A:B split** per the rule above.

## Current state (2026-09-01)
- Finite ground is **far from complete**: ~82 boards, only **1** has `download_mode`/`usb_serial`
  (`boot:coverage` → 81 on the worklist). Pinout/getting-started coverage unmeasured.
- ⇒ Right now the split should **favor Track A** (board boot/pinout/docs) while Track B keeps
  trickling new firmware — not pour everything into infinite firmware while the finite base is 1%.
