---
id: m5stick-s3__furble
type: recipe
board: m5stick-s3
firmware: furble
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stick-s3"
notes: "furble names this board as esp32-s3-devkitc-1 in its platformio.ini (env m5stick-s3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/gkoh/furble
  verified: '2026-09-21'
- field: flash.env
  url: https://github.com/gkoh/furble/blob/master/platformio.ini#L40
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/platformio.ini#L40
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/.github/workflows/main.yml
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/.github/workflows/release.yml
  verified: '2026-09-21'
---

# m5stick-s3 x furble

`furble` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5stick-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/gkoh/furble/blob/master/platformio.ini#L40
- rank 3 ci: `m5stick-s3` — https://github.com/gkoh/furble/blob/master/.github/workflows/main.yml
- rank 3 ci: `m5stick-s3` — https://github.com/gkoh/furble/blob/master/.github/workflows/release.yml
