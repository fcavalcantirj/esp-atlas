---
id: lolin-s2-mini
type: board
brand: lolin
name: LOLIN S2 mini
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: lolin-mini
price_tier: cheap
dimensions_mm:
- 34.3
- 25.4
usb:
  connector: usb-c
io:
  gpio_exposed: 27
  gpio_free: 27
notes:
- Based on ESP32-S2FN4R2; 4 MB flash, 2 MB PSRAM
- 27x digital I/O pins
- Pin-compatible with LOLIN D1 mini shields
- 'io.gpio_exposed=27 QUOTED: vendor page states "27x IO" (Features) and "Digital
  I/O Pins | 27" (Technical specs table); no enumerated GPIO pin-list/table is published
  in the spec table, so power_out is omitted'
- 'io.gpio_free=27 DERIVED: the vendor''s own labeled pinout diagram (s2_mini_v1.0.0
  silkscreen photo) enumerates exactly 27 header GPIO pads (1-18, 21, 33-40) -- matching
  the "27x IO" spec exactly. Of esp32-s2''s soc.reserved_pins, strapping 0/45/46 and
  usb_flash_tied 19/20 are all absent from this pad list (GPIO19/20 are consumed internally
  by the board''s native USB-C, and 45/46 by internal flash-voltage strapping), and
  the 2 MB PSRAM (ESP32-S2FN4R2, in-package) uses GPIO27-32 (SPI0 bus) which are likewise
  absent from the header -- so no reserved or onboard-consumed pin lands on an exposed
  pad: 27 - 0 = 27'
getting_started: https://www.wemos.cc/en/latest/s2/s2_mini.html
images:
  pinout: https://www.wemos.cc/en/latest/_images/s2_mini_v1.0.0_2_16x16.jpg
platformio_definitions:
- id: lolin_s2_mini
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 63abd8b75e3c94b3ac378f4c6011087c656454fd1499b731e13e9e63cb560c99
- id: lolin_s2_mini
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 4d93a5c5b7dc732018dcb7d434b0b80586a51d257a4fe2fb80415b26b0bd4b69
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/s2/s2_mini.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/s2/s2_mini.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://www.wemos.cc/en/latest/_images/s2_mini_v1.0.0_2_16x16.jpg
  verified: '2026-08-26'
- field: getting_started
  url: https://www.wemos.cc/en/latest/s2/s2_mini.html
  verified: '2026-09-12'
- field: images.pinout
  url: https://www.wemos.cc/en/latest/_images/s2_mini_v1.0.0_2_16x16.jpg
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/lolin_s2_mini.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/lolin_s2_mini.json
  verified: '2026-11-22'
---

# LOLIN S2 mini

Thumb-sized bare-S2 board: ESP32-S2FN4R2 (4 MB flash, 2 MB PSRAM), USB-C, 27 IO, D1-mini-shield compatible footprint.
