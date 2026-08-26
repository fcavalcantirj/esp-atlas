---
id: adafruit-feather-esp32-s3
type: board
brand: adafruit
name: Adafruit ESP32-S3 Feather (4MB Flash 2MB PSRAM)
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: feather
price_tier: medium
dimensions_mm:
- 52.3
- 22.7
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 20
  gpio_free: 16
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 'Main variant: 4 MB flash, 2 MB PSRAM; alternate: 8 MB flash, no PSRAM'
- MAX17048 battery monitor, JST LiPoly, NeoPixel, STEMMA QT
- 'io.power_out QUOTED: vendor page states "These pins are the output from the
  3.3V regulator, they can supply 500mA peak."'
- 'io.gpio_exposed=20 QUOTED: vendor pinouts page lists broken-out header pads D5,
  D6, D9, D10, D11, D12, D13 (7 digital), A0-A5 (6 analog, dual-named D8/D14-D18),
  SCK/MOSI/MISO (SPI), RX/TX (UART), SCL/SDA (I2C) = 20 GPIO-capable pads (RST/EN
  are control pins, not counted); same Feather pin-naming as adafruit-feather-esp32-s2.
  io.gpio_free=16 DERIVED: cross-referencing the vendor firmware repo''s own
  CircuitPython board pin-definition (pins.c) maps every header pad to GPIO3-4,
  5-6, 8-18, or 35-39 -- of esp32-s3''s soc.reserved_pins, GPIO3 (SDA, strapping)
  and GPIO35/36/37 (MOSI/SCK/MISO, usb_flash_tied) are exposed pads; NeoPixel/
  I2C_POWER/NEOPIXEL_POWER sit on GPIO7/21/33, off-header -- so 20 - 4 = 16'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5477
  verified: '2026-08-21'
- field: '*'
  url: https://learn.adafruit.com/adafruit-esp32-s3-feather/overview
  verified: '2026-08-21'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_feather_esp32s3_4mbflash_2mbpsram/pins.c
  verified: '2026-08-26'
---

# Adafruit ESP32-S3 Feather (4MB Flash 2MB PSRAM)

Feather-form ESP32-S3 board: native USB-C, LiPo JST + charging, NeoPixel, STEMMA QT.
