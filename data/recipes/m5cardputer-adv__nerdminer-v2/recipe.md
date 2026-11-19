---
id: m5cardputer-adv__nerdminer-v2
type: recipe
board: m5cardputer-adv
firmware: nerdminer-v2
status: unverified
chip_family: esp32-s3
flash:
  env: "M5-Cardputer-Adv"
notes: "nerdminer-v2 names this board as esp32-s3-devkitc-1 in its platformio.ini (env M5-Cardputer-Adv); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-11-19'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1198
  verified: '2026-11-19'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1198
  verified: '2026-11-19'
---

# m5cardputer-adv x nerdminer-v2

`nerdminer-v2` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1198
