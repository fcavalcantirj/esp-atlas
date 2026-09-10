---
id: m5stamp-s3__nerdminer-v2
type: recipe
board: m5stamp-s3
firmware: nerdminer-v2
status: unverified
chip_family: esp32-s3
flash:
  env: "M5-StampS3"
notes: "nerdminer-v2 names this board as m5stack-stamps3 in its platformio.ini (env M5-StampS3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1164
  verified: '2026-09-10'
- field: board
  url: https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1164
  verified: '2026-09-10'
---

# m5stamp-s3 x nerdminer-v2

`nerdminer-v2` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/BitMaker-hub/NerdMiner_v2/blob/main/platformio.ini#L1164
