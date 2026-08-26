---
id: lolin-s3
type: board
brand: lolin
name: LOLIN S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 65.3
- 25.4
usb:
  connector: usb-c
io:
  gpio_exposed: 31
  gpio_free: 27
notes:
- Based on ESP32-S3-WROOM-1; 16 MB flash (Quad SPI), 8 MB PSRAM (Octal SPI)
- 31x digital I/O pins
- 'Two Type-C USB ports: one native USB OTG, one UART bridge'
- Onboard LOLIN I2C port
- 'Weight: 9.0 g'
- 'io.gpio_exposed=31 QUOTED: vendor page states "31x IO" (Features) and "Digital
  I/O Pins | 31" (Technical specs table); no enumerated GPIO pin-list/table is
  published in the spec table, so power_out is omitted'
- 'io.gpio_free=27 DERIVED: the vendor''s own labeled pinout diagram (s3_v1.0.0
  silkscreen photo) enumerates exactly 31 header GPIO pads (0-18, 21, 38-48) --
  matching the "31x IO" spec exactly. Of esp32-s3''s soc.reserved_pins, strapping
  0/3/45/46 are all exposed (4 pins); usb_flash_tied 19/20/35/36/37 are all absent
  from the header (19/20 feed the native USB-OTG port directly, 35-37 the octal
  PSRAM/flash SPI0 bus) -- so 31 - 4 = 27'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/s3/s3.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/s3/s3.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://www.wemos.cc/en/latest/_images/s3_v1.0.0_2_16x16.jpg
  verified: '2026-08-26'
---

# LOLIN S3

Full-size ESP32-S3-WROOM-1 board: 16 MB flash, 8 MB PSRAM, dual Type-C (native OTG + UART bridge), onboard I2C port, 31 IO.
