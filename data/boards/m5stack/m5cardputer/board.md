---
id: m5cardputer
type: board
brand: m5stack
name: Cardputer
soc: esp32-s3
form_factor: m5-cardputer
price_tier: medium
dimensions_mm:
- 84.0
- 54.0
- 19.7
usb:
  bridge: native
power:
  battery_connector: true
  charging: true
display: 1.14in 240x135 ST7789V2
extras:
- sd-card
- mic
- speaker
notes:
- ESP32-S3FN8; 8 MB flash, no PSRAM
- 56-key QWERTY keyboard (4x14), SPM1423 MEMS mic, NS4168 8ohm/1W I2S speaker, IR
  emitter, microSD slot, 120mAh internal battery plus 1400mAh base battery; physical
  USB connector type not specified on the official page (omitted) — page lists "USB
  OTG, USB Serial/JTAG" (native ESP32-S3 USB, no separate bridge chip)
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-22'
---

# Cardputer

84x54mm ESP32-S3 pocket computer: QWERTY keyboard, 1.14in display, mic, speaker, IR emitter, microSD, dual built-in batteries.
