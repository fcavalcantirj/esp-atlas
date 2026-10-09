---
id: m5stamp-s3__daoa-mini-cardputeradv
type: recipe
board: m5stamp-s3
firmware: daoa-mini-cardputeradv
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer-adv"
notes: "daoa-mini-cardputeradv names this board as m5stack-stamps3 in its platformio.ini (env cardputer-adv); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/chatelp/daoa-mini-cardputeradv
  verified: '2026-10-09'
- field: flash.env
  url: https://github.com/chatelp/daoa-mini-cardputeradv/blob/master/platformio.ini#L12
  verified: '2026-10-09'
- field: board
  url: https://github.com/chatelp/daoa-mini-cardputeradv/blob/master/platformio.ini#L12
  verified: '2026-10-09'
---

# m5stamp-s3 x daoa-mini-cardputeradv

`daoa-mini-cardputeradv` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/chatelp/daoa-mini-cardputeradv/blob/master/platformio.ini#L12
