---
id: m5cardputer-adv__squachwatch-cyd
type: recipe
board: m5cardputer-adv
firmware: squachwatch-cyd
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer-adv"
notes: "squachwatch-cyd names this board as esp32-s3-devkitc-1 in its platformio.ini (env cardputer-adv); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/skizzophrenic/SquachWatch-CYD
  verified: '2026-11-15'
- field: flash.env
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L457
  verified: '2026-11-15'
- field: board
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L457
  verified: '2026-11-15'
---

# m5cardputer-adv x squachwatch-cyd

`squachwatch-cyd` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/skizzophrenic/SquachWatch-CYD/blob/master/platformio.ini#L457
