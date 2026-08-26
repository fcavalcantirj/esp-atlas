---
id: adafruit-matrixportal-s3
type: board
brand: adafruit
name: Adafruit MatrixPortal S3
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
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 8 MB flash, 2 MB PSRAM
- LIS3DH accelerometer onboard
- No battery connector or charging circuit
- Drives HUB75 RGB LED matrix panels; JST 3-pin analog-input connector; two user buttons plus reset
- 'io.power_out QUOTED: vendor page states "3V is the output from the 3.3V regulator,
  it can supply 500mA peak."'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5778
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-matrixportal-s3/pinouts
  verified: '2026-08-26'
---

# Adafruit MatrixPortal S3

ESP32-S3 board for driving HUB75 RGB LED matrices, with USB-C, STEMMA QT, and an onboard LIS3DH accelerometer.
