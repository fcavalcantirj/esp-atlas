---
id: lolin-s3-mini
type: board
brand: lolin
name: LOLIN S3 mini
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: lolin-mini
price_tier: cheap
dimensions_mm:
- 34.3
- 25.4
usb:
  bridge: native
extras:
- rgb-led
io:
  gpio_exposed: 27
notes:
- Based on ESP32-S3FH4R2; 4 MB flash, 2 MB PSRAM
- 27x digital I/O pins
- Onboard addressable RGB LED on IO47
- Native ESP32-S3 USB OTG; physical connector shape not stated on the official page
  (omitted)
- 'Weight: 3 g'
- 'io.gpio_exposed=27 QUOTED: vendor page states "27x IO" (Features) and "Digital
  I/O Pins | 27" (Technical specs table); no enumerated GPIO pin-list/table is
  published, so gpio_free and power_out are omitted'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/s3/s3_mini.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/s3/s3_mini.html
  verified: '2026-08-26'
---

# LOLIN S3 mini

Thumb-sized bare-S3 board: ESP32-S3FH4R2 (4 MB flash, 2 MB PSRAM), native USB OTG, onboard RGB LED on IO47, 27 IO.
