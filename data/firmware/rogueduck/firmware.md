---
id: rogueduck
type: firmware
name: M5StickS3 RogueDuck
url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
category: badusb
maintainer: M5RogueOps
socs:
- esp32-s3
distribution:
- m5burner
- releases
capabilities:
- badusb
requires:
- capability: native-usb
  why: BadUSB = USB HID device mode, which needs native USB-OTG on esp32-s2/s3; the
    classic esp32 cannot
  board_signal: native-usb
not_required:
- capability: wifi
  why: HID only
- capability: ble
- capability: psram
- capability: storage
popularity:
  stars: 4
  downloads: 152
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
  verified: '2026-09-01'
---

# M5StickS3 RogueDuck

M5StickS3 RogueDuck is a BadUSB firmware for the ESP32-S3-based M5StickC family.
