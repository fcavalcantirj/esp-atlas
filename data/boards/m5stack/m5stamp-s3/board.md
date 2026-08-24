---
id: m5stamp-s3
type: board
brand: m5stack
name: Stamp-S3
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-stamp
price_tier: cheap
dimensions_mm:
- 24.0
- 18.0
- 4.7
usb:
  connector: usb-c
extras:
- rgb-led
notes:
- ESP32-S3FN8; 8 MB flash. ESP32-S3FN8 ordering code has no PSRAM, per Espressif's ESP32-S3 series datasheet
- WS2812B-2020 programmable RGB LED, 23 GPIO exposed, no onboard battery
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/stamps3
  verified: '2026-08-22'
- field: psram_mb
  url: https://docs.m5stack.com/en/core/StampS3
  verified: '2026-08-24'
---

# Stamp-S3

24x18mm ESP32-S3 stamp module: USB-C, programmable RGB LED, 23 exposed GPIO.
