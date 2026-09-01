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
- **Finite ground = 100% covered → spend ALL effort on new (firmware/recipes).**
- **Finite ground has gaps → SPLIT effort:** part to *completing the finite ground* (backfill
  missing board fields, add missing boards/parts, complete docs), part to new firmware.

The split favors whichever is more starved; the finite part is the floor — the basics get
covered before pouring into the infinite.

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
