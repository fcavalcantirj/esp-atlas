---
id: esp32-c5-devkitc-1__bruce
type: recipe
board: esp32-c5-devkitc-1
firmware: bruce
status: reported
chip_family: esp32-c5
firmware_version: 1.16.1
flash:
  method: release-bin
  bin_url: https://github.com/BruceDevices/firmware/releases/download/1.16.1/Bruce-esp32-c5.bin
  offset: '0x0'
notes: "Bruce publishes a dedicated `Bruce-esp32-c5.bin` in its official 1.16.1 release. The ESP32-C5-DevKitC-1 is the reference bare C5 devkit (no display), so the plain c5 build is its target; the `-tft` variant is for C5 boards with a screen. Not independently hardware-verified by esp-atlas."
sources:
- field: 'flash.bin_url'
  url: https://github.com/BruceDevices/firmware/releases/download/1.16.1/Bruce-esp32-c5.bin
  verified: '2026-08-30'
- field: '*'
  url: https://github.com/pr3y/Bruce
  verified: '2026-08-30'
---

# esp32-c5-devkitc-1 x bruce

Bruce ships a dedicated `Bruce-esp32-c5.bin` in its 1.16.1 release. The
ESP32-C5-DevKitC-1 is the reference bare C5 devkit (no screen), so the plain c5
build targets it; the `-tft` variant is for C5 boards that carry a display.
Flashes in-browser via esp-atlas (release-bin → same-origin proxy).
