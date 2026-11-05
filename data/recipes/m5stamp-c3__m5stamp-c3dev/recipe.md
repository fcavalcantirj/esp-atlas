---
id: m5stamp-c3__m5stamp-c3dev
type: recipe
board: m5stamp-c3
firmware: m5stamp-c3dev
status: unverified
chip_family: esp32-c3
notes: "Not a drop-in for a bare M5Stamp C3. m5stamp-c3dev is the example ESP-IDF firmware for the author's own carrier board built around the M5Stamp C3, and it expects that carrier's peripherals: an ST7735 display and an SD card on SPI (SCLK 4, MOSI 5, MISO 6; SD CS 1; LCD CS 7, DC 10, RST 8, per main/c3dev_board.h at commit 61b7518). Setup per the pinned README: ESP-IDF release/v5.1, a recursive submodule checkout, the project's partition table, and separately prepared font and Wasm SPIFFS images. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/h1romas4/m5stamp-c3dev
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/h1romas4/m5stamp-c3dev/blob/61b7518d04d9f6b2f4266120f3d504028b748c07/main/c3dev_board.h
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/h1romas4/m5stamp-c3dev/blob/61b7518d04d9f6b2f4266120f3d504028b748c07/README.md
  verified: '2026-11-05'
---

m5stamp-c3dev on the M5Stamp C3 (ESP32-C3). `unverified`.

**This is the example firmware for a custom carrier board, not for a bare M5Stamp C3.**
It drives an ST7735 display and an SD card wired to specific pins:

| Signal | GPIO |
| --- | --- |
| SPI SCLK | 4 |
| SPI MOSI | 5 |
| SPI MISO | 6 |
| SD CS | 1 |
| LCD CS | 7 |
| LCD DC | 10 |
| LCD RST | 8 |

Building it needs ESP-IDF `release/v5.1`, a recursive submodule checkout, the
project's partition table, and separately prepared font and Wasm SPIFFS images.
No current successful build has been confirmed, and it has not been tested on
hardware for this atlas.
