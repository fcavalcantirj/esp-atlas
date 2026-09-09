---
id: m5stamp-s3__m5gotchi
type: recipe
board: m5stamp-s3
firmware: m5gotchi
status: unverified
chip_family: esp32-s3
flash:
  env: "Cardputer-dev"
notes: "m5gotchi names this board as m5stack-stamps3 in its platformio.ini (env Cardputer-dev); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Devsur11/M5Gotchi
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L13
  verified: '2026-09-08'
- field: board
  url: https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L13
  verified: '2026-09-08'
- field: board
  url: https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L45
  verified: '2026-09-08'
---

# m5stamp-s3 x m5gotchi

`m5gotchi` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L13
- rank 2 platformio: `m5stack-stamps3` — https://github.com/Devsur11/M5Gotchi/blob/main/platformio.ini#L45
