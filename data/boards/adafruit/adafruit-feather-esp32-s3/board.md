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
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 'Main variant: 4 MB flash, 2 MB PSRAM; alternate: 8 MB flash, no PSRAM'
- MAX17048 battery monitor, JST LiPoly, NeoPixel, STEMMA QT
- 'io.power_out QUOTED: vendor page states "These pins are the output from the
  3.3V regulator, they can supply 500mA peak."'
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
---

# Adafruit ESP32-S3 Feather (4MB Flash 2MB PSRAM)

Feather-form ESP32-S3 board: native USB-C, LiPo JST + charging, NeoPixel, STEMMA QT.
