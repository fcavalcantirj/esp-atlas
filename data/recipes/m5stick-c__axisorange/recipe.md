---
id: m5stick-c__axisorange
type: recipe
board: m5stick-c
firmware: axisorange
status: unverified
chip_family: esp32
flash:
  env: "m5stick-c"
notes: "axisorange names this board as m5stick-c in its platformio.ini (env m5stick-c); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/naninunenoy/AxisOrange
  verified: '2026-09-28'
- field: flash.env
  url: https://github.com/naninunenoy/AxisOrange/blob/master/platformio.ini#L13
  verified: '2026-09-28'
- field: board
  url: https://github.com/naninunenoy/AxisOrange/blob/master/platformio.ini#L13
  verified: '2026-09-28'
---

# m5stick-c x axisorange

`axisorange` declares `m5stick-c` in its platformio.ini; that name resolves to the catalogued board `m5stick-c` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stick-c` — https://github.com/naninunenoy/AxisOrange/blob/master/platformio.ini#L13
