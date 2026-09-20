---
id: m5stamp-s3__semi-evil-m5dial
type: recipe
board: m5stamp-s3
firmware: semi-evil-m5dial
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-stamps3"
notes: "semi-evil-m5dial names this board as m5stack-stamps3 in its platformio.ini (env m5stack-stamps3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/dagnazty/Semi-Evil-M5Dial
  verified: '2026-09-20'
- field: flash.env
  url: https://github.com/dagnazty/Semi-Evil-M5Dial/blob/main/platformio.ini#L13
  verified: '2026-09-20'
- field: board
  url: https://github.com/dagnazty/Semi-Evil-M5Dial/blob/main/platformio.ini#L13
  verified: '2026-09-20'
---

# m5stamp-s3 x semi-evil-m5dial

`semi-evil-m5dial` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/dagnazty/Semi-Evil-M5Dial/blob/main/platformio.ini#L13
