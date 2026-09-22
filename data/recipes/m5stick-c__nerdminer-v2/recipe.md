---
id: m5stick-c__nerdminer-v2
type: recipe
board: m5stick-c
firmware: nerdminer-v2
status: unverified
chip_family: esp32
flash:
  env: "M5Stick-C"
notes: "nerdminer-v2 names this board as m5stick-c in its platformio.ini (env M5Stick-C); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-22'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L62
  verified: '2026-09-22'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L62
  verified: '2026-09-22'
---

# m5stick-c x nerdminer-v2

`nerdminer-v2` declares `m5stick-c` in its platformio.ini; that name resolves to the catalogued board `m5stick-c` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stick-c` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L62
