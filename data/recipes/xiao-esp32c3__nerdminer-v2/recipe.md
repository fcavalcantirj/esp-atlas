---
id: xiao-esp32c3__nerdminer-v2
type: recipe
board: xiao-esp32c3
firmware: nerdminer-v2
status: unverified
chip_family: esp32-c3
flash:
  env: "ESP32-C3-super-mini"
notes: "nerdminer-v2 names this board as seeed_xiao_esp32c3 in its platformio.ini (env ESP32-C3-super-mini); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L371
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L371
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L502
  verified: '2026-09-10'
---

# xiao-esp32c3 x nerdminer-v2

`nerdminer-v2` declares `seeed_xiao_esp32c3` in its platformio.ini; that name resolves to the catalogued board `xiao-esp32c3` (esp32-c3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `seeed_xiao_esp32c3` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L371
- rank 2 platformio: `seeed_xiao_esp32c3` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L502
