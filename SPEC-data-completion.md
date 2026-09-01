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
