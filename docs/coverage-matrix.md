# Coverage matrix — run_guide / parse_intent

This is the human-readable companion to
[`apps/core/tests/test_coverage_matrix.py`](../apps/core/tests/test_coverage_matrix.py),
a reproducible, parametrized pytest suite that exercises `run_guide()` (and
`parse_intent()`'s firmware/build-filter branches) across diverse ESP32 chip
families, kinds and maker purposes, and pins the grounded ground truth for
each. Re-run it any time with:

```
make coverage
# or
npm run test:coverage
# or
scripts/coverage.sh
```

No network call is made — the LLM is stubbed dead throughout, so both the
model-explains-fit path (`run_guide`) and the model-maps-filters path
(`parse_intent`) are exercised purely against their own deterministic
retrieval, validation, and fallback logic.

## RUN cases (`run_guide(firmware)`)

| # | Firmware | Grounded teaching pinned |
|---|----------|---------------------------|
| 1 | `esp32marauder` | requires ⊇ {wifi, ble}; not_required ⊇ {psram, lora}; `m5cardputer` fit = ideal; `m5stick-cplus2` fit = works |
| 2 | `meshtastic` | requires = {lora, ble}; not_required ⊇ {psram, display}; `heltec-wifi-lora-32-v3` LoRa reason reads MET ("has"/"LoRa"), never "not verifiable"; `lilygo-t-beam` GPS reason MET; `xiao-esp32s3` LoRa NOT confirmed (no false on-board-LoRa claim) |
| 3 | `rogueduck` | requires = {native-usb}; boards = {`m5stick-s3`}; its fit = ideal |
| 4 | `wled` | requires ⊇ {wifi}; not_required ⊇ {psram, display}; `esp32-c3-devkitm-1` present, fit = ideal |
| 5 | `esphome` | requires ⊇ {wifi}; not_required ⊇ {psram}; recipe set includes `soldered-inkplate-10` & `soldered-inkplate-6` |
| 6 | `bruce` | requires ⊇ {wifi, ble}; `m5stack-core2` fit = works (native-usb unmet on plain esp32) |
| 7 | `launcher` | requires = {display}; not_required ⊇ {wifi, ble}; `m5cardputer` fit = ideal |
| 8 | `infiltra` | requires ⊇ {wifi, ble, sub-ghz} |
| 9 | `m5-crystal` | requires ⊇ {wifi, ble, rfid-nfc, ir} |
| 10 | `m5stick-nemo` | requires ⊇ {wifi, ble, ir} |

## BUILD/intent cases (`parse_intent(query)`)

| # | Query | Mapped filters asserted |
|---|-------|--------------------------|
| 11 | "a wifi 6 board" | `filters.radio == "wifi-6"` |
| 12 | "thread zigbee matter smart-home mesh" | `filters.ieee802154 == true` |
| 13 | "esp32-s3 board with 8mb psram" | `filters.psram_min == 8` and `filters.soc == "esp32-s3"` |
| 14 | "a battery powered wearable" | `filters.battery == true` |
| 15 | "esp32-c6 with native usb" | `filters.soc == "esp32-c6"` and `filters.usb_native == true` |

These five inject a stub LLM that returns the on-target filter mapping (the
NL→filters judgment call is a model call, not a deterministic function) and
assert that `validate_filters`/`parse_intent`'s own plumbing carries it
through intact — i.e. that nothing a maker asked for is silently dropped or
corrupted en route to the wizard. None needed `xfail`: every filter key/value
above is deterministically checkable against the live index (`wifi-6`,
`esp32-s3`, `esp32-c6`, `psram_min=8` are all real facet values; the boolean
needs `ieee802154`/`battery`/`usb_native` require no data lookup at all).

## Golden oracle — real-Groq acceptance (not this file's test)

The five BUILD/intent cases above (and every case in
`apps/core/tests/test_intent_oracle.py`) inject a stub/fake LLM: they prove
our own plumbing (validation, kind selection) never breaks, but they cannot
catch Groq itself being inconsistent about WHEN to infer a spec from a vague
purpose noun. Measured on prod (2026-08-25): "cheap wearable" → `battery`,
"esp32 with a camera" → `psram_min:2`, but "waterproof gps tracker" and
"build a plant monitoring system" → nothing. Same rule, applied unevenly.

`apps/core/tests/data/inference_golden.py` pins ~20 curated queries against
the ONE consistent rule the tightened `SYSTEM_PROMPT` (`esp_atlas_core.intent`)
now states explicitly: map a filter only when a word names a spec directly,
or the goal is literally unavoidable without it (camera → PSRAM framebuffer,
worn/wearable → battery, serve-a-web-UI → Wi-Fi + PSRAM). A bare purpose noun
— monitor, tracker, system, gadget, detector, sensor — is never a guessed
filter; it goes to `unmapped`.

Two ways to run the SAME matrix against REAL inference (network required,
non-deterministic, therefore never in the blocking CI job):

```
make inference-oracle                                   # HTTP against prod by default
ESP_ATLAS_API=http://localhost:8000 make inference-oracle
GROQ_API_KEY=... make inference-oracle                   # direct GroqClient, no HTTP hop
# or, as a pytest run (skipped unless one of the above env vars is set):
pytest -m inference
```

`scripts/inference_oracle.py` prints a per-query PASS/FAIL table and a
summary, and exits non-zero on any failure — the acceptance gate for this
work is pasting that table's output, not a green fast suite alone (the fast
suite cannot exercise Groq's actual judgment at all).

## Coverage table: firmware → covered?

| Firmware | RUN case | Boards in recipe graph |
|----------|----------|--------------------------|
| `esp32marauder` | ✅ #1 | m5cardputer, m5stick-cplus2 |
| `meshtastic` | ✅ #2 | heltec-wifi-lora-32-v3, heltec-wireless-paper, heltec-wireless-tracker, lilygo-t-beam, lilygo-t-deck, lilygo-t-watch-s3, m5stack-cores3, xiao-esp32s3 |
| `rogueduck` | ✅ #3 | m5stick-s3 |
| `wled` | ✅ #4 | adafruit-matrixportal-s3, esp32-c3-devkitm-1, esp32-c6-devkitc-1, esp32-c6-devkitm-1, esp32-s3-devkitc-1, lolin-s2-mini, lolin-s3-mini |
| `esphome` | ✅ #5 | heltec-wifi-lora-32-v3, lilygo-t-display-s3, lilygo-t-dongle-s3, m5atoms3-lite, m5dial, m5nanoc6, m5stack-core2, m5stack-cores3, m5stick-cplus2, soldered-inkplate-10, soldered-inkplate-6 |
| `bruce` | ✅ #6 | lilygo-t-deck, lilygo-t-display-s3, lilygo-t-embed, lilygo-t-watch-s3, m5cardputer, m5stack-core2, m5stack-cores3, m5stick-cplus2, m5stick-s3 |
| `launcher` | ✅ #7 | lilygo-t-deck, lilygo-t-display-s3, lilygo-t-display-s3-amoled, lilygo-t-dongle-s3, lilygo-t-embed, m5cardputer, m5stack-core2, m5stack-cores3, m5stick-cplus2, m5stick-s3 (widest firmware in the dataset) |
| `infiltra` | ✅ #8 | m5cardputer, m5stick-cplus2 |
| `m5-crystal` | ✅ #9 | m5stick-cplus2, m5stick-s3 |
| `m5stick-nemo` | ✅ #10 | m5cardputer |

**10/10 seeded firmware have a RUN case.** `test_every_firmware_has_a_run_case`
in the test file fails the build if a new `data/firmware/<id>/` is added
without extending `RUN_MATRIX` (and this table) to match — coverage cannot
silently regress as the dataset grows.

## Coverage table: chip family → has any firmware recipe?

| Chip family (`data/socs/`) | Any firmware recipe? |
|------------------------------|------------------------|
| `esp32` | ✅ yes |
| `esp32-s2` | ✅ yes |
| `esp32-s3` | ✅ yes |
| `esp32-c3` | ✅ yes |
| `esp32-c6` | ✅ yes |
| `esp32-c2` | ❌ **no** |
| `esp32-c5` | ❌ **no** |
| `esp32-c61` | ❌ **no** |
| `esp32-h2` | ❌ **no** |
| `esp32-h4` | ❌ **no** |
| `esp32-p4` | ❌ **no** |

6 of 11 seeded chip families have boards and SoC records but zero seeded
firmware recipes running on them — see Known Gap (a) below.

## Known gaps

These are real, verbatim gaps in the current dataset/model, surfaced here
rather than papered over. Each is tracked as future work in
[`ROADMAP.md`](../ROADMAP.md).

**(a) Six chip families have boards/SoCs but ZERO firmware recipes.**
`esp32-h2`, `esp32-p4`, `esp32-c2`, `esp32-c5`, `esp32-c61`, and `esp32-h4`
each have seeded SoC records (`data/socs/`) and at least one board built on
them, but no `data/recipes/*.md` names any board in these families. A maker
on one of these chips gets zero `run_guide` answers today — not because the
firmware doesn't support the chip, but because no recipe has been authored
yet.

**(b) Bruce's per-tool capabilities are modeled as flat hard `requires`, but
they are actually OPTIONAL per-feature.** `bruce`'s `requires` array lists
`native-usb`, `sub-ghz`, `rfid-nfc`, and `ir` alongside `wifi`/`ble` — but
Bruce runs fine with only Wi-Fi + BLE; BadUSB/sub-GHz/NFC/IR are each an
independent on-device *tool* that works only if that specific peripheral is
present, not a firmware-wide gate. Today's model has no way to say "hard
requirement" vs. "this one feature needs this one peripheral" — both are
`requires` entries and both currently count toward `_fit_for`'s hardware-match
ratio identically, which understates fit on boards missing an unrelated tool's
peripheral (e.g. a board with Wi-Fi+BLE but no CC1101 reads as a worse fit
than it should for a maker who only wants the Wi-Fi/BLE tools).

**(c) `lilygo-t-watch-s3`'s board record has an empty `display` field, though
it is a smartwatch with a screen.** `data/boards/lilygo/lilygo-t-watch-s3/board.md`
has no `display:` frontmatter field at all (a data gap, not a hardware fact) —
so `launcher`'s `display` requirement, whose `board_signal` reads that exact
field, reads "lacks it" for a board that plainly has a screen, and
`run_guide("launcher")` reports T-Watch S3's fit as `unconfirmed` rather than
`ideal`.

**(d) ESPHome's PSRAM need is conditional, and the binary `not_required` flag
cannot express that.** ESPHome does not need PSRAM in general — but it DOES
require PSRAM when driving a large display framebuffer that exceeds the
~520KB ESP32 SRAM budget (e.g. the 9.7in Inkplate-10, which ships 8MB PSRAM
for exactly this reason). `esphome`'s `firmware.md` already documents this
nuance in its `not_required[].why` prose, but the schema only has a flat
`not_required: [psram]` — there is no per-board or per-config field to flip
PSRAM from "not needed" to "needed" when a large-framebuffer display is in
play. Today this is taught honestly in prose but not enforced structurally.
