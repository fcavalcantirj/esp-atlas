---
id: m5stamp-s3__m5porkchop
type: recipe
board: m5stamp-s3
firmware: m5porkchop
status: unverified
chip_family: esp32-s3
flash:
  env: "m5cardputer-debug"
notes: "m5porkchop names this board as m5stack-stamps3 in its platformio.ini (env m5cardputer-debug); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/0ct0sec/M5PORKCHOP
  verified: '2026-09-09'
- field: flash.env
  url: https://github.com/0ct0sec/M5PORKCHOP/blob/main/platformio.ini#L5
  verified: '2026-09-09'
- field: board
  url: https://github.com/0ct0sec/M5PORKCHOP/blob/main/platformio.ini#L5
  verified: '2026-09-09'
---

# m5stamp-s3 x m5porkchop

`m5porkchop` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/0ct0sec/M5PORKCHOP/blob/main/platformio.ini#L5
