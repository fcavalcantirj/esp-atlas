---
id: esp32-c3-devkitm-1__nerdminer-v2
type: recipe
board: esp32-c3-devkitm-1
firmware: nerdminer-v2
status: unverified
chip_family: esp32-c3
flash:
  env: "ESP32-C3-devKitmv1"
notes: "nerdminer-v2 names this board as esp32-c3-devkitm-1 in its platformio.ini (env ESP32-C3-devKitmv1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L404
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L404
  verified: '2026-09-10'
---

# esp32-c3-devkitm-1 x nerdminer-v2

`nerdminer-v2` declares `esp32-c3-devkitm-1` in its platformio.ini; that name resolves to the catalogued board `esp32-c3-devkitm-1` (esp32-c3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-c3-devkitm-1` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L404
