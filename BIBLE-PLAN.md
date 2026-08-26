# esp-atlas → the Bible of ESP32 — delivery plan

> **MOTTO: 100% of esp-atlas info is verified and verifiable.** (see `CLAUDE.md`)
>
> Living tracker. **One task at a time, slowly, each verified + landed before the
> next.** North star: answer the question no other resource answers well — *"will
> THIS board do MY project, and exactly how do I wire it?"* Every task obeys the
> house rules: SPEC before code, oracle/TDD first, cite-or-omit, verify the real
> path before declaring done, land on main.
>
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done+verified+shipped.
> Each task notes its kind (spec/code/data/web) and how it will be verified.

## Done already (this thread)
- [x] io-power schema (`board.io`, `soc.drive`, `soc.reserved_pins`) + validate owner-rule
- [x] SoC layer: `drive` 11/11, `reserved_pins` 10/11 (h4 omitted — no source), `esp32-s31` created (datasheet-verified)
- [x] board `io` sweep: `gpio_free` 33/78, cite-or-omit, 20 boards honestly omitted
- [x] `io_heavy` build-guide exclusion + **fallback-supplement fix** — 4-strip/4-fan query now surfaces a full-header devkit (verified real recipe path, `esp32-devkitc-v4` + "17 usable GPIO")
- [x] Launcher-as-discovery adapter (`SPEC-discovery §2`) + first ingest: firmware 10 → 16, cited, `unverified`

---

## Phase A — Foundation: completeness + reliability (feeds everything)

- [x] **A1 — Deterministic-first `io_heavy`** *(code · reliability)* — SHIPPED `87d7191`
  `_deterministic_io_heavy()` ORs a code-computed signal onto Groq's boolean and
  never lets the model pull a clearly-io-heavy goal back to False. Verified with a
  False-returning stub LLM: 4+4 and "6 relays + 3 servos" surface 3 devkits (pin-
  poor excluded); "plant monitor" / "blink one LED" stay non-io-heavy. Golden +
  unit-table in `test_build_guide.py`; SPEC-io-power.md §6.2.
  - [ ] *(deferred, separate)* `clarify` question-selection: its confidence gate is
    already deterministic (LLM only picks question ids), so this is a smarter-default
    concern for its own SPEC-clarify.md pass, not a reliability bug. Tracked, not now.

- [x] **A2 — io coverage wide** *(data)* — DONE. `gpio_free` **33→72/78 (92%)**, any-io 75/78.
  Run as 8 vendor batches (buffer-safe, compact sources) after the all-at-once run hit
  the 1MB message-buffer crash. 6 honest omits (5 LilyGo display/wearable + sparkfun
  micromod M.2) — no defensible official pinout, correctly left blank. All cited.
  *(esp32-h4 reserved_pins still omitted — no official source yet.)*

- [ ] **B moved ahead of A3.** Rationale: io data is now rich enough (72/78) to build
  the crown jewel; A3 (wider board catalog) is open-ended breadth that doesn't block B.

- [ ] **A3 — board catalog wide** *(data · big, batched)*
  Grow beyond 78 toward the real ESP32 board universe (official Arduino index,
  Launcher devices, vendor pages) via the population lane, batched + human-merged.
  *Verify:* per-batch coverage report, no trust-bar regressions.

## Phase B — 🏆 The crown jewel: Pin Planner + Power Budget

- [~] **B1 — SPEC + data-sufficiency spike** *(spec)* — `SPEC-pin-planner.md` WRITTEN.
  Spike finding: `gpio_free` is a count, real pin NUMBERS are prose-only, `reserved_pins`
  is structured. BLOCKER → new `io.gpio_pins` field (structurable from existing notes).
  Awaiting Felipe red-pen (Q1 v1-scope, Q2 structure-notes, Q3 plan-across-all-boards)
  before B1-data + B2 build.

- [ ] **B2 — Pin Planner backend** *(code · `/plan`)*
  Input: peripherals (I²C, SPI, UART, N strips, M PWM, ADC…). Output for a board:
  a valid GPIO assignment avoiding strapping/input-only/flash-tied, or a hard
  "doesn't fit" with the reason. Deterministic. *Verify:* golden on the 4+4 case.

- [ ] **B3 — Power Budget advisor** *(code · part of `/plan`)*
  `power_out.rail_ma_max` + `soc.drive` vs estimated peripheral draw → verdict
  ("external 5–12 V + MOSFET, board sends PWM only"). *Verify:* golden.

- [ ] **B4 — Pin Planner UI** *(web)*
  The interactive planner on the site. *Verify:* drive the real flow (dogfood).

## Phase C — Detail-page richness

- [ ] **C1 — Schematic / pinout IMAGES on detail pages** *(schema + data + web)* ← Felipe asked
  New cited fields `pinout_image` / `schematic_url` (board + soc), populated from
  Espressif hardware-design-guidelines (e.g. esp32h2/schematic-checklist) + vendor
  pinouts; render on the board/SoC detail page. *Verify:* image loads on prod page.

- [ ] **C2 — Gotcha warnings from `reserved_pins`** *(code + web)*
  Turn raw reserved pins into guidance on board pages ("GPIO0 = boot, don't use
  for output"). *Verify:* warnings render for a known board.

- [ ] **C3 — `/compare` endpoint + UI** *(code + web)*
  Side-by-side spec diff for N boards. *Verify:* compare two real boards.

## Phase D — Buyer / practical completeness

- [ ] **D1 — new selection-factor schema fields** *(schema)*
  price / buy+availability links, operating temp, certs (FCC/CE), antenna type
  (PCB/IPEX/ext), header pitch. Cite-or-omit.
- [ ] **D2 — populate D1 fields** *(data · population lane)*

## Phase E — Community surface

- [ ] **E1 — discovery `example` entity** *(data)* — "what people built" per board, from the Launcher/discovery lane.
- [ ] **E2 — grow firmware catalog** *(data)* — further curated discovery runs.

---

## Working agreement
- Sequential: finish + verify + land one box before opening the next.
- Each code/data task → coder-delegate, oracle/TDD first, branch → I verify the
  **real path** → land on main → confirm on prod where user-visible.
- Specs (B1, C-series schema) I may author directly, then delegate the build.
- Prod verify respects the ~1h Vercel `/api` cache (curl `/api`, not HTML).
