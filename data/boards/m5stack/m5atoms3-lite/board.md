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
  gpio_free: 6
notes:
- ESP32-S3FN8; 8 MB flash, no PSRAM
- WS2812C-2020 programmable RGB LED, IR transmitter LED, programmable button, HY2.0-4P
  interface, no onboard battery
- 'io.gpio_exposed=6 QUOTED: vendor page states "IO Interface x6", pins G5/G6/G7/G8/G38/G39.
  The page separately lists an HY2.0-4P Grove port (G1/G2) not covered by that
  "IO Interface" tally -- kept out of gpio_exposed since the vendor''s own count
  doesn''t include it. io.gpio_free=6 DERIVED: subtracting esp32-s3''s soc.reserved_pins
  (strapping {0,3,45,46}, usb_flash_tied {19,20,35,36,37}) -- none of G5/G6/G7/G8/G38/G39
  fall in either set -- gives 6 - 0 = 6. No max Grove/rail output current stated
  on this page, so power_out is omitted.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/AtomS3%20Lite
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/AtomS3%20Lite
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/AtomS3%20Lite
  verified: '2026-08-26'
---

# AtomS3-Lite

24x24mm ESP32-S3 atom unit without display: programmable RGB LED, IR transmitter, USB-C.
