---
id: lolin-s2-mini__nerdminer-v2
type: recipe
board: lolin-s2-mini
firmware: nerdminer-v2
status: unverified
chip_family: esp32-s2
flash:
  env: "ESP32-S2-mini-wemos"
notes: "nerdminer-v2 names this board as lolin_s2_mini in its platformio.ini (env ESP32-S2-mini-wemos); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L272
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L272
  verified: '2026-09-10'
---

# lolin-s2-mini x nerdminer-v2

`nerdminer-v2` declares `lolin_s2_mini` in its platformio.ini; that name resolves to the catalogued board `lolin-s2-mini` (esp32-s2). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `lolin_s2_mini` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L272
