---
id: adafruit-metro-esp32-s3
type: board
brand: adafruit
name: Adafruit Metro ESP32-S3 (16MB Flash 8MB PSRAM)
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: metro
price_tier: medium
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
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 400
notes:
- 16 MB flash, 8 MB Octal PSRAM, 512 KB SRAM
- LiPoly battery connector with built-in charging; MAX17048 I2C battery monitor
- STEMMA QT connector with switchable power; JTAG 2x5 debug header; Revision B (Nov 2023) fixed NeoPixel/SPI/SD-card pin conflicts with PSRAM
- Dimensions not specified on the product page (omitted)
- 'io.power_out QUOTED: vendor page states "This is the output pin from the 3.3V
  regulator, you can grab up to 400mA from this regulator for accessories, it''s
  also used by the ESP32-S3 which can have spiky current draw."'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5500
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-metro-esp32-s3/pinouts
  verified: '2026-08-26'
---

# Adafruit Metro ESP32-S3

Arduino Uno-form-factor ESP32-S3 board with native USB-C, 16 MB flash / 8 MB PSRAM, LiPoly charging, and STEMMA QT.
