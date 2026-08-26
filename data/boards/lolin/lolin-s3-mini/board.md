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
  gpio_free: 23
notes:
- Based on ESP32-S3FH4R2; 4 MB flash, 2 MB PSRAM
- 27x digital I/O pins
- Onboard addressable RGB LED on IO47
- Native ESP32-S3 USB OTG; physical connector shape not stated on the official page
  (omitted)
- 'Weight: 3 g'
- 'io.gpio_exposed=27 QUOTED: vendor page states "27x IO" (Features) and "Digital
  I/O Pins | 27" (Technical specs table); no enumerated GPIO pin-list/table is
  published in the spec table, so power_out is omitted'
- 'io.gpio_free=23 DERIVED: the vendor''s own labeled pinout diagram (s3_mini_v1.0.0
  silkscreen photo) enumerates exactly 27 header GPIO pads (1-18, 21, 33-38, 43,
  44) -- matching the "27x IO" spec exactly; GPIO47 (the onboard RGB LED) is not
  among them, confirming it is off-header and needs no separate subtraction. Of
  esp32-s3''s soc.reserved_pins, strapping GPIO3 is exposed (1 pin; 0/45/46 are
  not on the header); usb_flash_tied 35/36/37 are exposed (3 pins; 19/20 are not,
  consumed internally by native USB) -- so 27 - 1 - 3 = 23'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/s3/s3_mini.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/s3/s3_mini.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://www.wemos.cc/en/latest/_images/s3_mini_v1.0.0_2_16x16.jpg
  verified: '2026-08-26'
---

# LOLIN S3 mini

Thumb-sized bare-S3 board: ESP32-S3FH4R2 (4 MB flash, 2 MB PSRAM), native USB OTG, onboard RGB LED on IO47, 27 IO.
