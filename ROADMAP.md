# Roadmap

## In progress / this PR

### Debug — "Verify my board"

Client-side debug rail (`SPEC-verify.md`), complementing the flash rail
(#43): a board page can now check esp-atlas's cited `soc`/`flash_mb`/
`psram_mb` against the live connected chip over Web Serial (esptool-js
`ESPLoader.detectChip()`, read-only — no stub upload, no flash write), and
open a serial monitor to watch the firmware's own UART output live. No
backend involved; the pure field-comparison matcher (`lib/verify-board.ts`)
is unit-tested, the Web Serial/esptool-js I/O path is browser-only and
verified by build + manual hardware test. Per-board GPIO pinout (below)
remains future work — this closes the "debug it" half of the tagline, not
the wiring-level question.

## Future

### 1. Per-board GPIO pinout data

Every board's GPIO pinout — which physical pin maps to which chip GPIO, which
pins are strapping/boot-mode pins, which are exposed on a header vs. reserved
for onboard peripherals (flash, PSRAM, USB, a built-in display/IMU/LoRa
radio) — varies board-to-board even within the same chip family, and **is not
in the dataset today**. `schema/board.schema.json` has no `pinout` field, and
no `data/boards/**/board.md` records one.

This matters for run_guide/wizard once a maker asks a wiring-level question
("which pin do I solder the CC1101 CS to on a XIAO ESP32-C6?") — today the
dataset can answer "does this board have the peripheral" but not "where do I
connect a new one."

Planned shape:
- A new **future board field** (schema addition to `board.schema.json`), e.g.
  `pinout: [{ "pin": "GPIO9", "header_label": "D9", "role": "gpio" | "strapping" | "reserved", "reserved_for": "onboard-lora" | null }, ...]` —
  sourced from the same official datasheet/pinout-diagram citation rule as
  every other field (`sources[]`, no guessing).
- A **future UI**: a rendered pinout diagram/table on each board's page,
  and (longer term) a `run_guide` teaching point like "connect your sub-GHz
  module's CS to GPIO_X, the only free SPI-capable pin on this board."

### 2. The four KNOWN GAPS from `docs/coverage-matrix.md`

Tracked here as future work; see that document for full detail on each.

- **(a) Zero-recipe chip families.** `esp32-h2`, `esp32-p4`, `esp32-c2`,
  `esp32-c5`, `esp32-c61`, and `esp32-h4` each have seeded SoC/board records
  but no firmware recipe targets any board in these families yet. Future
  work: author recipes (or confirm and document that none of today's 10
  firmware projects support these chips, if that turns out to be true) so
  `run_guide` stops going silent for makers on these chips.

- **(b) Bruce's per-tool capabilities need a hard-vs-optional distinction.**
  `bruce`'s `requires` currently lists `native-usb`, `sub-ghz`, `rfid-nfc`,
  and `ir` flatly alongside the true hard needs `wifi`/`ble` — but each of
  those four is only needed for its own on-device tool, not to run Bruce at
  all. Future work: extend `schema/firmware.schema.json`'s `requires[]` with
  a way to mark an entry as per-feature/optional (e.g. `hard: false` or a
  separate `optional_features[]` array), and update `run_guide._fit_for` so
  an unmet optional feature never drags fit down the way an unmet hard
  requirement does.

- **(c) `lilygo-t-watch-s3` has no `display` field despite having a screen.**
  A data-entry gap, not a hardware fact — its `board.md` needs a `display:`
  value (with a source citation) so `launcher`'s display requirement reads
  MET instead of leaving its fit at `unconfirmed`. Future work: audit other
  boards with a known onboard screen (smartwatches, T-Deck-style keyboards)
  for the same silently-missing field.

- **(d) ESPHome's PSRAM requirement is conditional, and the schema can't
  express that.** `not_required` is a flat boolean-per-capability list, so it
  cannot say "not needed, except when driving a large-framebuffer display."
  Future work: either a per-recipe override (a recipe can declare a
  capability its firmware generally doesn't need, but *this* board/config
  does — e.g. `soldered-inkplate-10__esphome` overriding the `psram`
  `not_required` back to required) or a firmware-level conditional rule keyed
  on a board's own `display` field size. Either way, this should turn today's
  prose-only `why` explanation into something `_fit_for` can actually gate on.

### 3. JTAG step-through debugging

"Verify my board" (see **In progress / this PR** above) shipped the chip-
identity check and the live serial monitor. A JTAG-style step-through for
boards that expose it is a further-out extension of the same debug rail —
not built, not scheduled.
