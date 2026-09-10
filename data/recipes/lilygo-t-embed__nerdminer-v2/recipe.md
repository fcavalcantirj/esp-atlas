---
id: lilygo-t-embed__nerdminer-v2
type: recipe
board: lilygo-t-embed
firmware: nerdminer-v2
status: unverified
chip_family: esp32-s3
flash:
  env: "Lilygo-T-Embed"
notes: "nerdminer-v2 names this board as esp32-s3-devkitc-1 in its platformio.ini (env Lilygo-T-Embed); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L642
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L642
  verified: '2026-09-10'
---

# lilygo-t-embed x nerdminer-v2

`nerdminer-v2` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `lilygo-t-embed` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L642
