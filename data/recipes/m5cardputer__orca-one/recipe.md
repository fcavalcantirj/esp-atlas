---
id: m5cardputer__orca-one
type: recipe
board: m5cardputer
firmware: orca-one
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-cardputer"
notes: "orca-one names this board as m5stack-stamps3 in its platformio.ini (env m5stack-cardputer); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/OceanTroop/orca-one
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L118
  verified: '2026-09-10'
- field: board
  url: https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L118
  verified: '2026-09-10'
---

# m5cardputer x orca-one

`orca-one` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5cardputer` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L118
