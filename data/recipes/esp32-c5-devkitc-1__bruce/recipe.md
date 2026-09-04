---
id: esp32-c5-devkitc-1__bruce
type: recipe
board: esp32-c5-devkitc-1
firmware: bruce
status: known-good
chip_family: esp32-c5
firmware_version: 1.16.1
flash:
  method: release-bin
  bin_url: https://github.com/BruceDevices/firmware/releases/download/1.16.1/Bruce-esp32-c5.bin
  offset: '0x0'
notes: "Bruce publishes a dedicated `Bruce-esp32-c5.bin` in its official 1.16.1 release. The ESP32-C5-DevKitC-1 is the reference bare C5 devkit (no display), so the plain c5 build is its target; the `-tft` variant is for C5 boards with a screen. Verified on real hardware 2026-09-01: ESP32-C5-DevKitC-1, chip revision v1.2 (ROM esp32c5-eco3-20250704), ESP32-C5-WROOM-1 with 8 MB flash and no PSRAM. Bruce-esp32-c5.bin 1.16.1 (4,122,608 bytes, bootloader at 0x2000 inside the merged image) written at 0x0 with esptool 5.3.0 over the USB-to-UART port (CP2102N), hash verified, 211 s at 115200 (the C5 ROM does not support --baud changes). Boots cleanly: ROM -> second-stage -> app, no resets in a 10 s window; logs one 'MSPI Timing: Failed to allocate dummy cacheline for PSRAM memory barrier' error (module has no PSRAM - harmless) and one 'Invalid IO 255' pin warning. Headless board: Bruce runs on its serial CLI. CAVEAT: the in-browser flash of this same image through ESP Web Tools 10.4.0 fails on this silicon revision with 'Failed to initialize. Try resetting your device or holding the BOOT button while clicking INSTALL.' - esptool-js 0.6.1 does not know this chip's CHIP magic 0x30e1706f (espressif/esptool-js#262; chip-id detection merged upstream in #197, unreleased). Flash from a terminal until esptool-js ships a release and ESP Web Tools bumps."
sources:
- field: 'flash.bin_url'
  url: https://github.com/BruceDevices/firmware/releases/download/1.16.1/Bruce-esp32-c5.bin
  verified: '2026-09-01'
- field: '*'
  url: https://github.com/BruceDevices/firmware
  verified: '2026-08-30'
---

# esp32-c5-devkitc-1 x bruce

Bruce ships a dedicated `Bruce-esp32-c5.bin` in its 1.16.1 release. The
ESP32-C5-DevKitC-1 is the reference bare C5 devkit (no screen), so the plain c5
build targets it; the `-tft` variant is for C5 boards that carry a display.

**Known-good on hardware (2026-09-01).** Flashed on a real ESP32-C5-DevKitC-1
(chip rev v1.2, ESP32-C5-WROOM-1, 8 MB flash, no PSRAM): `Bruce-esp32-c5.bin`
1.16.1 written at `0x0` with esptool 5.3.0 over the CP2102N USB-to-UART port,
hash-verified, boots cleanly to the Bruce serial CLI (the board is headless).
**Terminal flash only for now:** the in-browser path (ESP Web Tools 10.4.0 /
esptool-js 0.6.1) fails on this silicon — esptool-js doesn't yet recognise the
C5's chip magic `0x30e1706f` (espressif/esptool-js#262). Flash from a terminal
until esptool-js ships the chip-id fix and ESP Web Tools bumps.
