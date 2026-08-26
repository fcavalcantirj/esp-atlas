---
id: m5cardputer__esp32-bit-pirate
type: recipe
board: m5cardputer
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
firmware_version: v1.7
flash:
  method: web-flasher
sources:
- field: '*'
  url: https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/
  verified: '2026-08-26'
- field: 'firmware_version'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/releases/tag/v1.7
  verified: '2026-08-26'
---

# m5cardputer x esp32-bit-pirate

ESP32 Bit Pirate's supported-devices table explicitly lists the M5 Cardputer (screen,
keyboard, mic, speaker, IR TX, SD card, battery, standalone mode); it also flashes via
M5Burner under the Cardputer category.
