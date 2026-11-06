---
id: lilygo-t-watch-s3__squachwatch-cyd
type: recipe
board: lilygo-t-watch-s3
firmware: squachwatch-cyd
status: unverified
chip_family: esp32-s3
flash:
  env: "twatch-s3"
notes: "squachwatch-cyd names this board as esp32-s3-devkitc-1 in its platformio.ini (env twatch-s3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/skizzophrenic/SquachWatch-CYD
  verified: '2026-11-06'
- field: flash.env
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L392
  verified: '2026-11-06'
- field: board
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L392
  verified: '2026-11-06'
---

# lilygo-t-watch-s3 x squachwatch-cyd

`squachwatch-cyd` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `lilygo-t-watch-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L392
