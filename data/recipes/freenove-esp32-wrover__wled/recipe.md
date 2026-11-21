---
id: freenove-esp32-wrover__wled
type: recipe
board: freenove-esp32-wrover
firmware: wled
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "wled names this board as ESP32_WROVER in its release (asset WLED_16.0.1_ESP32_WROVER.bin) (release v16.0.1); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names freenove-esp32-wrover."
sources:
- field: '*'
  url: https://github.com/wled/WLED
  verified: '2026-11-18'
- field: board
  url: https://github.com/wled/WLED/releases/tag/v16.0.1
  verified: '2026-11-18'
---

# freenove-esp32-wrover x wled

`wled` declares `ESP32_WROVER` in its release; that name resolves to the catalogued board `freenove-esp32-wrover` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `ESP32_WROVER` — https://github.com/wled/WLED/releases/download/v16.0.1/WLED_16.0.1_ESP32_WROVER.bin
