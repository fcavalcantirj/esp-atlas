---
id: m5stick-c__orca-one
type: recipe
board: m5stick-c
firmware: orca-one
status: unverified
chip_family: esp32
flash:
  env: "m5stack-cplus1_1"
notes: "orca-one names this board as m5stick-c in its platformio.ini (env m5stack-cplus1_1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/OceanTroop/orca-one
  verified: '2026-09-22'
- field: flash.env
  url: https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L31
  verified: '2026-09-22'
- field: board
  url: https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L31
  verified: '2026-09-22'
- field: board
  url: https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L73
  verified: '2026-09-22'
---

# m5stick-c x orca-one

`orca-one` declares `m5stick-c` in its platformio.ini; that name resolves to the catalogued board `m5stick-c` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stick-c` — https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L31
- rank 2 platformio: `m5stick-c` — https://github.com/OceanTroop/orca-one/blob/main/platformio.ini#L73
