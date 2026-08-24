---
id: m5nanoc6
type: board
brand: m5stack
name: NanoC6
soc: esp32-c6
flash_mb: 4
psram_mb: 0
form_factor: m5-nano
price_tier: cheap
dimensions_mm:
- 23.5
- 12.0
- 9.5
usb:
  connector: usb-c
extras:
- rgb-led
notes:
- ESP32-C6FH4; 4 MB flash
- WS2812 programmable RGB LED, IR transmitter, button on GPIO9, Grove interface,
  ceramic antenna, no onboard battery
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/M5NanoC6
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
---

# NanoC6

23.5x12mm ESP32-C6 nano unit: programmable RGB LED, IR transmitter, Grove port, USB-C.
