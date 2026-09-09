---
id: m5stick-s3__m5gotchi
type: recipe
board: m5stick-s3
firmware: m5gotchi
status: unverified
chip_family: esp32-s3
flash:
  env: "m5sticks3"
notes: "m5gotchi names this board as esp32-s3-devkitc-1 in its platformio.ini (env m5sticks3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Devsur11/M5Gotchi
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L76
  verified: '2026-09-08'
- field: board
  url: https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L76
  verified: '2026-09-08'
---

# m5stick-s3 x m5gotchi

`m5gotchi` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5stick-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L76
