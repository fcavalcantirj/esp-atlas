---
id: lolin-s2-mini__wled
type: recipe
board: lolin-s2-mini
firmware: wled
status: known-good
chip_family: esp32-s2
flash:
  method: web-flasher
notes: "Dedicated `[env:lolin_s2_mini]` environment; this is WLED's official ESP32-S2 build."
sources:
- field: '*'
  url: https://raw.githubusercontent.com/wled/WLED/main/platformio.ini
  verified: '2026-08-24'
---

# lolin-s2-mini x wled

Dedicated `[env:lolin_s2_mini]` environment; this is WLED's official ESP32-S2 build.
