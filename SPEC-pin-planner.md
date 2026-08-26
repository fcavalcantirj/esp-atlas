# SPEC — Pin Planner + Power Budget (the crown jewel)

> Status: DRAFT (living). The feature that makes esp-atlas the Bible: **"will THIS
> board do MY project, and exactly how do I wire it?"** Builds directly on the
> io-power layer (`SPEC-io-power.md`). No build until agreed. Spiked against real
> data first (§2) — the spike changed the plan.

## 1. Problem

`/build` now answers *which board* for a project (io_heavy → excludes pin-poor,
surfaces devkits). The Bible-level next step is *how to wire it*: given a project's
peripherals, produce a **concrete GPIO assignment** on a chosen board — or a hard
"doesn't fit" with the reason — plus a **power verdict**. No ESP32 resource does
this. It's the full end-to-end answer to the r/esp32 "4 strips + 4 fans" question:
not just "use a DevKitC" but "strip1→GPIO4, strip2→GPIO5, … fan1→GPIO16 (PWM), and
those loads need an external 5 V rail + MOSFETs, the board only sends the signal."

## 2. Spike — the data is NOT sufficient yet (verified 2026-08-26)

Checked real records before speccing. Finding:

- `io.gpio_free` is a **count** (e.g. `esp32-s3-devkitc-1: 27`), **not** a pin list.
- The actual exposed GPIO **numbers** exist **only as prose** in the derivation
  notes (*"J1 = GPIO 3-18,46; J3 = GPIO 0-2,19-21,35-45,47,48"*).
- `soc.reserved_pins` **is** structured (`strapping:[0,3,45,46]`,
  `usb_flash_tied:[19,20,35,36,37]`).

**Conclusion: a planner cannot assign pins from today's data** — it has the count
and the reserved list, but not the *structured set of usable pin numbers* per board.
**Mitigant:** the pin-number lists already exist in the notes, so structuring them
is a data-shaping task, not new research. This is the gate for B2.

## 3. Data additions

**3a. `board.io.gpio_pins` — the structured exposed-pin set (REQUIRED for the planner).**
```jsonc
"gpio_pins": { "type": "array", "items": {"type":"number"},
  "description": "the GPIO NUMBERS broken out to a user-accessible header (the raw exposed set, before subtracting reserved). Cited to the same pinout source as gpio_exposed/gpio_free." }
```
Populated by structuring the pin lists already in each board's derivation notes;
cite-or-omit (a board with no defensible pinout keeps no `gpio_pins`, and the
planner simply can't plan on it — honest). `gpio_free` stays as the headline count;
`gpio_pins` is the machine-usable set. Invariant: `len(gpio_pins − reserved_pins −
consumed) == gpio_free` (a cross-check the validator can assert).

**3b. `soc` pin-capability table — for capability-aware assignment (v2, optional).**
ADC-capable pins, touch pins, input-only (already in `reserved_pins.input_only`).
v1 does NOT need this (see §5 scope); flagged so v1's schema leaves room.

## 4. The planner — deterministic, no LLM in the assignment

`POST /plan {board_id, peripherals:[...]}` →
```
free = board.io.gpio_pins  −  soc.reserved_pins(strapping,input_only,usb_flash_tied)  −  display/PSRAM-consumed
assign each peripheral's signal lines from `free` (greedy, stable order)
→ {assignments:[{peripheral, signal, gpio}], fits:bool, leftover:int, unmet:[...], power:{...}}
```
- **Deterministic**: pure set arithmetic + a fixed assignment order. No model call —
  the Bible can't guess a pin.
- **Peripheral pin-needs** are a fixed code table (I²C=2 [SDA,SCL], SPI=3-4, UART=2
  [RX,TX], each addressable strip=1 data, each PWM fan=1, digital sensor=1, ADC
  sensor=1 [v2: must be an ADC pin]). Same "code-defined, never LLM" discipline as
  clarify's `_CATALOG` and build-guide's `_channel_count`.
- **No-fit is a first-class answer**: when `need > len(free)`, return `fits:false`
  with exactly which lines are unmet — the honest "this board can't do it."

## 5. Scope — v1 ships digital/PWM; v2 adds capability-awareness

- **v1 (build now):** assign digital/PWM/data lines (addressable strips, PWM fans,
  relays, servos, digital sensors, I²C/SPI/UART) from `free`. On ESP32 these route
  through the GPIO matrix, so *any* free pin works — set arithmetic is correct and
  complete. This already fully answers the 4-strips+4-fans case.
- **v2 (later):** ADC/touch/DAC-specific assignment needs the §3b capability table
  (ADC channels are fixed pins). Flagged, not built. v1 marks ADC needs as
  "assign to any free pin, verify ADC capability" rather than silently mis-assigning.

## 6. Power Budget (B3) — folds into `/plan`

Using `board.io.power_out.rail_ma_max` + `soc.drive` (per-pad mA) vs a fixed
per-peripheral draw table:
- A GPIO sources ~tens of mA (`soc.drive`) — never a motor/strip. So the planner's
  power verdict ALWAYS states: signal pins carry logic only; **driven loads (fans,
  strips) need an external rail through a MOSFET/driver**, and checks that rail
  against `rail_ma_max` when the board even offers one.
- Output: `power:{signal_ok:true, load_note:"4 fans + 4 strips ≈ N A — external 5–12 V + MOSFET; board's rail is 600 mA, USB-dependent"}`.

## 7. Non-negotiables

1. **Every assigned pin traces to cited data** — `gpio_pins` (cited pinout) minus
   `reserved_pins` (cited datasheet/guidelines). Nothing invented.
2. **Deterministic** — set arithmetic + fixed order + code peripheral table. No LLM
   in the assignment path; reproducible byte-for-byte.
3. **Honest no-fit** — under-capacity returns `fits:false` + unmet lines, never a
   partial/guessed map.
4. **Cite-or-omit** — a board without `gpio_pins` is un-plannable and says so; never
   fabricate a pin set.
5. **TDD, oracle-first** — golden: `/plan` for the 4+4 goal on `esp32-s3-devkitc-1`
   returns a full valid assignment (every strip/fan/sensor/UART line → a real free
   GPIO, none reserved) + the external-power note; and on a pin-poor board returns
   `fits:false` with the unmet lines.

## 8. Task breakdown (updates BIBLE-PLAN.md Phase B)

- **B1 (this spec) + data:** add `io.gpio_pins`, structure it from existing notes
  across the 72 boards that have `gpio_free`. cite-or-omit. *(data · batched like A2)*
- **B2:** `/plan` backend — deterministic assignment. *(code · golden-first)*
- **B3:** power verdict in `/plan`. *(code)*
- **B4:** planner UI. *(web · dogfood)*

## 9. Open questions for Felipe

- **Q1** — v1 digital/PWM only (ADC "any free pin, verify"), ship the capability
  table (§3b) as v2? I lean yes — it fully answers the driving cases now.
- **Q2** — `gpio_pins` populated by *structuring existing notes* (cheap, no re-fetch)
  vs re-deriving from source. I lean structure-the-notes, spot-verify against source.
- **Q3** — planner input: pick a board first then plan, or "plan across all boards →
  here's the cheapest that fits"? The latter is more Bible-like (and reuses io_heavy).
