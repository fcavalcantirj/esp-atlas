---
id: esp32-devkitc-v4__tasmota
type: recipe
board: esp32-devkitc-v4
firmware: tasmota
status: unverified
chip_family: esp32
firmware_version: v15.6.0
flash:
  method: web-flasher
sources:
- field: '*'
  url: https://tasmota.github.io/install/
  verified: '2026-08-26'
- field: 'firmware_version'
  url: https://github.com/arendst/Tasmota/releases/tag/v15.6.0
  verified: '2026-08-26'
---

# esp32-devkitc-v4 x tasmota

Tasmota's generic `tasmota32` build targets plain ESP32 hardware with no board-specific
driver requirements; the Espressif ESP32-DevKitC-V4 is the reference ESP32 board and
flashes via the official Tasmota WebInstaller.
