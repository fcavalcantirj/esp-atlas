---
id: adafruit-matrixportal-s3
type: board
brand: adafruit
name: Adafruit MatrixPortal S3
aka:
- adafruit_matrixportal_esp32s3
soc: esp32-s3
flash_mb: 8
psram_mb: 2
form_factor: matrixportal
price_tier: medium
dimensions_mm:
- 63.6
- 44.3
- 20.0
usb:
  connector: usb-c
extras:
- rgb-led
- stemma-qt
- imu
io:
  gpio_exposed: 9
  gpio_free: 8
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 8 MB flash, 2 MB PSRAM
- LIS3DH accelerometer onboard
- No battery connector or charging circuit
- Drives HUB75 RGB LED matrix panels; JST 3-pin analog-input connector; two user buttons
  plus reset
- 'io.power_out QUOTED: vendor page states "3V is the output from the 3.3V regulator,
  it can supply 500mA peak."'
- 'io.gpio_exposed=9 QUOTED: vendor pinouts page lists A0 (3-pin JST analog connector)
  plus header pads A1-A4, TXO/RXI (UART), SCL/SDA (I2C/STEMMA QT) = 9 GPIO-capable
  pads; D13 is explicitly the onboard status LED only ("not listed among the available
  I/O connectors"), and BUTTON_UP/BUTTON_DOWN are dedicated internal button pins with
  no general-breakout alias in the vendor firmware repo''s pin-definition, so neither
  is counted. io.gpio_free=8 DERIVED: cross-referencing that same CircuitPython board
  pin-definition (pins.c) maps A1 to GPIO3, which is esp32-s3''s only exposed soc.reserved_pins
  hit (strapping); the HUB75 matrix connector, LIS3DH interrupt, and NeoPixel are
  wired to dedicated non-header pins (GPIO2/35-48, GPIO15, GPIO4) that never reach
  the header -- so 9 - 1 = 8'
getting_started: https://learn.adafruit.com/adafruit-matrixportal-s3
images:
  photo: https://cdn-learn.adafruit.com/guides/images/000/003/849/medium800thumb/5778-06.gif
sources:
- field: '*'
  url: https://www.adafruit.com/product/5778
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-matrixportal-s3/pinouts
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-matrixportal-s3/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_matrixportal_s3/pins.c
  verified: '2026-08-26'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/adafruit_matrixportal_esp32s3.json
  verified: '2026-09-07'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-matrixportal-s3
  verified: '2026-09-12'
- field: images
  url: https://learn.adafruit.com/adafruit-matrixportal-s3
  verified: '2026-09-12'
---

# Adafruit MatrixPortal S3

ESP32-S3 board for driving HUB75 RGB LED matrices, with USB-C, STEMMA QT, and an onboard LIS3DH accelerometer.
