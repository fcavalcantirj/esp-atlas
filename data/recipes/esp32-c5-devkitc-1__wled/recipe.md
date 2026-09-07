---
id: esp32-c5-devkitc-1__wled
type: recipe
board: esp32-c5-devkitc-1
firmware: wled
status: unverified
chip_family: esp32-c5
flash:
  env: "esp32c5dev"
notes: "wled names this board as esp32-c5-devkitc-1 in its platformio.ini (env esp32c5dev); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/wled/WLED
  verified: '2026-09-07'
- field: flash.env
  url: https://github.com/wled/WLED/blob/main/platformio.ini#L552
  verified: '2026-09-07'
- field: board
  url: https://github.com/wled/WLED/blob/main/platformio.ini#L552
  verified: '2026-09-07'
- field: board
  url: https://github.com/wled/WLED/blob/main/platformio.ini#L571
  verified: '2026-09-07'
---

# esp32-c5-devkitc-1 x wled

`wled` declares `esp32-c5-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `esp32-c5-devkitc-1` (esp32-c5). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-c5-devkitc-1` — https://github.com/wled/WLED/blob/main/platformio.ini#L552
- rank 2 platformio: `esp32-c5-devkitc1-n8r4` — https://github.com/wled/WLED/blob/main/platformio.ini#L571
