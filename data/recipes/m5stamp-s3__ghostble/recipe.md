---
id: m5stamp-s3__ghostble
type: recipe
board: m5stamp-s3
firmware: ghostble
status: unverified
chip_family: esp32-s3
flash:
  env: "ghostble_sticks3"
notes: "ghostble names this board as m5stack-stamps3 in its platformio.ini (env ghostble_sticks3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/SmonSE/GhostBLE
  verified: '2026-09-19'
- field: flash.env
  url: https://github.com/SmonSE/GhostBLE/blob/main/platformio.ini#L26
  verified: '2026-09-19'
- field: board
  url: https://github.com/SmonSE/GhostBLE/blob/main/platformio.ini#L26
  verified: '2026-09-19'
---

# m5stamp-s3 x ghostble

`ghostble` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/SmonSE/GhostBLE/blob/main/platformio.ini#L26
