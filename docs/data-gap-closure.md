# Data-gap closure plan — cover the basics, well

Mission (README + north-star): *hold a board → **identify it** → **flash the best firmware**
→ **wire it up (pinout)**.* The finite ground (SPEC-data-completion.md) must reach ~100%.

Live gauge (boards, 2026-09-09): download_mode **12%** · usb_serial **22%** · pinout **17%**
· getting_started **18%** · dimensions 61% · form_factor 91% · usb_connector 76%. The USE
basics (flash/wire/start) are ~85% empty — the site says *what* a board is, not *how to use it*.

## Oracle-verified source (Espressif esp-dev-kits user guides), 7-board probe

| field | groundable? | how | notes |
|---|---|---|---|
| **getting_started** | ✅ ~100% | the board's `user_guide.html` URL (exists for every devkit) | not currently set at all → cheap win |
| **pinout** (`io.gpio_pins`) | ✅ high | parse the **"Header Block"** HTML `<table>`; GPIO→function rows (C3 17, C6 25, S2 39) | schema already has `io.gpio_pins`; 15/90 filled |
| **image** (pin layout) | ✅ high | pin-layout diagram URL in the doc | **schema has NO image field** — needs a schema add first |
| **usb_serial** | ⚠️ partial | bridge chip the doc names; FTDI (FT2232) currently missed → add token | many devkits say only "USB-to-UART bridge" → need a curated model→chip fallback map |
| **download_mode** | ✅ most | the "Holding down Boot … pressing Reset … Download mode" sentence | FTDI/auto boards (WROVER) need the auto branch |
| doc URL coverage | ⚠️ | `board_user_guide_url()` formula | `esp32-devkitc-v4`, `esp32-s3-devkitc-1` slugs differ → fetch-fail; needs alias/URL map |

## Closure steps (each a bot-PR, TDD, cite-or-omit)

1. **getting_started = user_guide URL** when the doc fetches OK. Near-100%. [status: in progress]
2. **usb_serial broaden**: add FTDI (`ft2232`,`ft232`) + native-JTAG slash form; then a curated
   `board→bridge` fallback for docs that don't name the chip. [status: in progress]
3. **pinout backfill**: parse the Header Block table → `io.gpio_pins`. Highest mission value. [todo]
4. **image**: add `image` to `schema/board.schema.json` (guard-safe, optional) + backfill the
   pin-layout diagram URL so visual board-ID works. [todo]
5. **doc-URL map**: per-board doc URL / alias for slugs the formula misses. [todo]
6. **missing popular boards** (Track A "missing boards"): ESP32-CAM, ESP32 DevKit V1, XIAO
   ESP32-S3, Super Mini — the most-searched boards absent from the atlas. [todo]

Each field stays **cite-or-omit**: a value is written only with the source URL that proves it;
never guessed (a wrong download step or pin can brick a board / mislead a build).
