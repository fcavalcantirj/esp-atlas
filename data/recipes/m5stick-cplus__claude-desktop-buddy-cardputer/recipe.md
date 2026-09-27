---
id: m5stick-cplus__claude-desktop-buddy-cardputer
type: recipe
board: m5stick-cplus
firmware: claude-desktop-buddy-cardputer
status: unverified
chip_family: esp32
flash:
  env: "m5stickc-plus"
notes: "claude-desktop-buddy-cardputer names this board as m5stick-c in its platformio.ini (env m5stickc-plus); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer
  verified: '2026-09-27'
- field: flash.env
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L3
  verified: '2026-09-27'
- field: board
  url: https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L3
  verified: '2026-09-27'
---

# m5stick-cplus x claude-desktop-buddy-cardputer

`claude-desktop-buddy-cardputer` declares `m5stick-c` in its platformio.ini; that name resolves to the catalogued board `m5stick-cplus` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stick-c` — https://github.com/y88huang/claude-desktop-buddy-cardputer/blob/main/platformio.ini#L3
