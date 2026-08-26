---
id: adafruit-qt-py-esp32-s3
type: board
brand: adafruit
name: Adafruit QT Py ESP32-S3 WiFi Dev Board with STEMMA QT (8MB Flash No PSRAM)
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: qt-py
price_tier: cheap
dimensions_mm:
- 21.7
- 17.8
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 11
  gpio_free: 8
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 600
notes:
- 8 MB flash, no PSRAM (this product, 5426); a separate 4 MB flash / 2 MB PSRAM variant is sold as product 5700
- Battery input pads on underside with diode protection for external packs up to 6V; no onboard charging circuit
- 'io.gpio_exposed=11 QUOTED: vendor page states "There are eleven GPIO pins broken
  out to pads."'
- 'io.power_out QUOTED: vendor page states "These pins are the output from the
  3.3V regulator, they can supply 600mA peak."'
- 'io.gpio_free=8 DERIVED: cross-referencing the vendor firmware repo''s own
  CircuitPython board pin-definition (pins.c) maps the eleven pads to GPIO5-9,
  16-18, 35-37 -- of esp32-s3''s soc.reserved_pins, GPIO35/36/37 (MOSI/SCK/MISO,
  usb_flash_tied) are among them; the BOOT button (GPIO0) and the STEMMA QT
  connector''s dedicated I2C (SCL1/SDA1, GPIO40/41) and NeoPixel (GPIO38/39) sit
  off the eleven counted pads -- so 11 - 3 = 8'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5426
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s3/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s3/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_qtpy_esp32s3_nopsram/pins.c
  verified: '2026-08-26'
---

# Adafruit QT Py ESP32-S3

Tiny ESP32-S3 board with native USB-C, STEMMA QT, RGB NeoPixel, and 8 MB flash / no PSRAM.
