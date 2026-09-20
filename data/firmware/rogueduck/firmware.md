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
  stars: 6
  forks: 1
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
  verified: '2026-09-01'
- field: summary
  url: https://github.com/M5RogueOps/M5StickS3-RogueDuck
  verified: '2026-09-20'
summary: "RogueDuck V2.1 is a custom firmware for the M5Stack StickS3 that turns the\
  \ device into a dual\u2011mode (AP\u202F+\u202FSTA) USB HID BadUSB platform with\
  \ a mobile\u2011first web interface for uploading, editing, and executing DuckyScript\
  \ payloads, cloud\u2011fetching scripts, and exfiltrating data, plus a CRT\u2011\
  style UI and hardware controls for injection and pocket lock."
readme_lang: en
readme_sha: 7d86d8e8d35ddbfcd104c6641b54f687bf256ac4b1da76cfb7fe1f92aaba1b76
---

# M5StickS3 RogueDuck

M5StickS3 RogueDuck is a BadUSB firmware for the ESP32-S3-based M5StickC family.
