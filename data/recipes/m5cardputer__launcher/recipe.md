---
id: m5cardputer__launcher
type: recipe
board: m5cardputer
firmware: launcher
status: known-good
chip_family: esp32-s3
firmware_version: 2.8.0
flash:
  method: release-bin
  bin_url: https://github.com/bmorcelli/Launcher/releases/download/2.8.0/Launcher-m5stack-cardputer.bin
  offset: '0x0'
sources:
- field: 'flash.bin_url'
  url: https://github.com/bmorcelli/Launcher/releases/download/2.8.0/Launcher-m5stack-cardputer.bin
  verified: '2026-08-24'
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-08-23'
---

# m5cardputer x launcher

Launcher lists the M5Cardputer among its supported devices.
