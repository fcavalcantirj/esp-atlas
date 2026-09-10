---
id: m5stamp-s3__raising-hell-cardputer
type: recipe
board: m5stamp-s3
firmware: raising-hell-cardputer
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer_adv_dev"
notes: "raising-hell-cardputer names this board as m5stack-stamps3 in its platformio.ini (env cardputer_adv_dev); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/acpayers-alt/raising-hell-cardputer
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/acpayers-alt/raising-hell-cardputer/blob/main/platformio.ini#L3
  verified: '2026-09-10'
- field: board
  url: https://github.com/acpayers-alt/raising-hell-cardputer/blob/main/platformio.ini#L3
  verified: '2026-09-10'
- field: board
  url: https://github.com/acpayers-alt/raising-hell-cardputer/blob/main/platformio.ini#L40
  verified: '2026-09-10'
---

# m5stamp-s3 x raising-hell-cardputer

`raising-hell-cardputer` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/acpayers-alt/raising-hell-cardputer/blob/main/platformio.ini#L3
- rank 2 platformio: `m5stack-stamps3` — https://github.com/acpayers-alt/raising-hell-cardputer/blob/main/platformio.ini#L40
