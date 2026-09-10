---
id: m5stamp-s3__pigtail
type: recipe
board: m5stamp-s3
firmware: pigtail
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-stamps3"
notes: "pigtail names this board as m5stack-stamps3 in its platformio.ini (env m5stack-stamps3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/benbaker76/Pigtail
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/benbaker76/Pigtail/blob/main/platformio.ini#L13
  verified: '2026-09-10'
- field: board
  url: https://github.com/benbaker76/Pigtail/blob/main/platformio.ini#L13
  verified: '2026-09-10'
---

# m5stamp-s3 x pigtail

`pigtail` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/benbaker76/Pigtail/blob/main/platformio.ini#L13
