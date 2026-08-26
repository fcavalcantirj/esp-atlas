---
id: m5atoms3-lite
type: board
brand: m5stack
name: AtomS3-Lite
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-atom
price_tier: cheap
dimensions_mm:
- 24.0
- 24.0
- 9.5
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_exposed: 6
notes:
- ESP32-S3FN8; 8 MB flash, no PSRAM
- WS2812C-2020 programmable RGB LED, IR transmitter LED, programmable button, HY2.0-4P
  interface, no onboard battery
- 'io.gpio_exposed=6 QUOTED: vendor page states "IO Interface x6", pins G5/G6/G7/G8/G38/G39'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/AtomS3%20Lite
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/AtomS3%20Lite
  verified: '2026-08-26'
---

# AtomS3-Lite

24x24mm ESP32-S3 atom unit without display: programmable RGB LED, IR transmitter, USB-C.
