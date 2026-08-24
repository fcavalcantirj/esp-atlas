---
id: lilygo-t-dongle-s3__launcher
type: recipe
board: lilygo-t-dongle-s3
firmware: launcher
status: known-good
chip_family: esp32-s3
firmware_version: 2.8.0
flash:
  method: release-bin
  bin_url: https://github.com/bmorcelli/Launcher/releases/download/2.8.0/Launcher-lilygo-t-dongle-s3-tft.bin
  offset: '0x0'
sources:
- field: 'flash.bin_url'
  url: https://github.com/bmorcelli/Launcher/releases/download/2.8.0/Launcher-lilygo-t-dongle-s3-tft.bin
  verified: '2026-08-24'
- field: '*'
  url: https://github.com/bmorcelli/Launcher/wiki/Supported-devices
  verified: '2026-08-23'
---

# lilygo-t-dongle-s3 x launcher

Launcher runs on the LilyGo T-Dongle-S3, per its official Supported-devices list.
