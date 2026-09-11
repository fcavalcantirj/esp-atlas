---
id: adafruit-qt-py-esp32-s3-no-psram
type: board
brand: adafruit
name: Adafruit QT Py ESP32-S3 WiFi Dev Board with STEMMA QT (8 MB Flash No PSRAM)
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
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 11
notes:
- 8 MB flash, no PSRAM (product 5426).
- 'flash_mb=8 / psram_mb=0 QUOTED: product page states "8MB Flash, 512KB SRAM, no
  PSRAM"; title "Adafruit QT Py ESP32-S3 WiFi Dev Board with STEMMA QT - 8 MB Flash
  / No PSRAM".'
- 'SOURCE NOTE: the universe manifest lists this id''s source_url as
  adafruit.com/product/5700, but that product page is the *2 MB PSRAM / 4 MB flash*
  variant ("Adafruit QT Py S3 with 2MB PSRAM"). The no-PSRAM 8 MB board this id
  names is product 5426, which is cited here so psram_mb=0 is grounded (cite-or-omit).'
- 'dimensions_mm QUOTED: "Product Dimensions: 21.7mm x 17.8mm x 5.7mm" (height 5.7
  mm omitted; two-axis footprint recorded).'
- 'usb.bridge=native / usb_serial QUOTED: "native USB" and "ESP32-S3 Dual Core
  240MHz Tensilica processor ... with native USB"; esp32-s3 exposes native
  USB-Serial-JTAG.'
- 'Battery input pads on underside with diode protection for external packs up to
  6V; no onboard charging. QUOTED: "Battery input pads on underside with diode
  protection for external battery packs up to 6V input".'
- 'io.gpio_exposed=11 QUOTED: product page states "13 GPIO pins: 11 on breakout
  pads, 2 more on QT connector" -- 11 pads recorded (gpio_free omitted, not
  vendor-printed).'
- 'extras QUOTED: "Built-in RGB NeoPixel LED with power control" and "STEMMA QT
  connectors for the I2C bus".'
- 'aka omitted: the arduino-esp32 FQBN adafruit_qtpy_esp32s3_nopsram is already
  carried by the existing adafruit-qt-py-esp32-s3 record for the same product, so
  it is not duplicated here.'
getting_started: https://learn.adafruit.com/adafruit-qt-py-esp32-s3
sources:
- field: '*'
  url: https://www.adafruit.com/product/5426
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s3
  verified: '2026-09-11'
---

# Adafruit QT Py ESP32-S3 (No PSRAM)

Tiny ESP32-S3 board with native USB-C, STEMMA QT, RGB NeoPixel, and 8 MB flash / no PSRAM (product 5426).
