---
id: m5stamp-s3__zx-spectrum-cardputer-internal
type: recipe
board: m5stamp-s3
firmware: zx-spectrum-cardputer-internal
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-cardputer-adv"
notes: "zx-spectrum-cardputer-internal names this board as m5stack-stamps3 in its platformio.ini (env m5stack-cardputer-adv); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external/blob/main/platformio.ini#L7
  verified: '2026-09-10'
- field: board
  url: https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external/blob/main/platformio.ini#L7
  verified: '2026-09-10'
---

# m5stamp-s3 x zx-spectrum-cardputer-internal

`zx-spectrum-cardputer-internal` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external/blob/main/platformio.ini#L7
