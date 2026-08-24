---
id: xiao-esp32s3__meshtastic
type: recipe
board: xiao-esp32s3
firmware: meshtastic
status: known-good
chip_family: esp32-s3
flash:
  method: web-flasher
notes: "Build target `seeed_xiao_s3`. The XIAO ESP32S3 has no LoRa radio of its own: the documented setup pairs it with the Wio-SX1262 module."
sources:
- field: '*'
  url: https://meshtastic.org/docs/hardware/devices/seeed-studio/wio-series/
  verified: '2026-08-24'
---

# xiao-esp32s3 x meshtastic

Build target `seeed_xiao_s3`. The XIAO ESP32S3 has no LoRa radio of its own: the documented setup pairs it with the Wio-SX1262 module.
