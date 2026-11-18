---
id: m5cardputer-adv__claude-desktop-buddy-cardputer
type: recipe
board: m5cardputer-adv
firmware: claude-desktop-buddy-cardputer
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer-adv"
notes: "claude-desktop-buddy-cardputer names this board as m5stack-stamps3 in its platformio.ini (env cardputer-adv); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer
  verified: '2026-11-18'
- field: flash.env
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L19
  verified: '2026-11-18'
- field: board
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L19
  verified: '2026-11-18'
---

# m5cardputer-adv x claude-desktop-buddy-cardputer

`claude-desktop-buddy-cardputer` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L19
