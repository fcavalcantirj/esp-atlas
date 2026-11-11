---
id: m5stamp-s3__adversary
type: recipe
board: m5stamp-s3
firmware: adversary
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer_release"
notes: "adversary names this board as m5stack-stamps3 in its platformio.ini (env cardputer_release); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Isonimus/adversary
  verified: '2026-11-11'
- field: flash.env
  url: https://github.com/Isonimus/adversary/blob/main/platformio.ini#L58
  verified: '2026-11-11'
- field: board
  url: https://github.com/Isonimus/adversary/blob/main/platformio.ini#L58
  verified: '2026-11-11'
---

# m5stamp-s3 x adversary

`adversary` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/Isonimus/adversary/blob/main/platformio.ini#L58
