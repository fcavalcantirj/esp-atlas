---
id: m5stamp-s3__m5stack-cardputer-ssh
type: recipe
board: m5stamp-s3
firmware: m5stack-cardputer-ssh
status: unverified
chip_family: esp32-s3
flash:
  env: "m5cardputer-adv"
notes: "m5stack-cardputer-ssh names this board as m5stack-stamps3 in its platformio.ini (env m5cardputer-adv); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/MangoX0567/M5Stack-Cardputer-SSH
  verified: '2026-09-19'
- field: flash.env
  url: https://github.com/MangoX0567/M5Stack-Cardputer-SSH/blob/main/platformio.ini#L6
  verified: '2026-09-19'
- field: board
  url: https://github.com/MangoX0567/M5Stack-Cardputer-SSH/blob/main/platformio.ini#L6
  verified: '2026-09-19'
---

# m5stamp-s3 x m5stack-cardputer-ssh

`m5stack-cardputer-ssh` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/MangoX0567/M5Stack-Cardputer-SSH/blob/main/platformio.ini#L6
