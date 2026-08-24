---
id: m5stamp-c3
type: board
brand: m5stack
name: Stamp-C3
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: m5-stamp
price_tier: cheap
dimensions_mm:
- 34.0
- 20.0
- 4.6
usb:
  connector: usb-c
extras:
- rgb-led
notes:
- ESP32-C3; 4 MB flash
- SK6812 programmable RGB LED, 13 GPIO exposed, no onboard battery
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Stamp_C3
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
---

# Stamp-C3

34x20mm ESP32-C3 stamp module: USB-C, programmable RGB LED, 13 exposed GPIO.
