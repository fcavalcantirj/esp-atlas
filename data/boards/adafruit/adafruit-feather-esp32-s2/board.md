---
id: adafruit-feather-esp32-s2
type: board
brand: adafruit
name: Adafruit ESP32-S2 Feather (4MB Flash 2MB PSRAM)
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: feather
price_tier: medium
dimensions_mm:
- 52.4
- 22.8
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
- 4 MB flash, 2 MB PSRAM
- JST-PH LiPoly connector with built-in USB-C charging; battery monitor chip (originally LC709203, updated to MAX17048 as of June 2023)
- STEMMA QT connector with switchable power; On/Charge/User status LEDs; Reset and DFU (BOOT0) buttons
- 'io.power_out QUOTED: vendor page states "3.3V - These pins are the output from
  the 3.3V regulator, they can supply 500mA peak."'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5000
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s2-feather/pinouts
  verified: '2026-08-26'
---

# Adafruit ESP32-S2 Feather

Feather-form ESP32-S2 board with native USB-C, LiPoly JST charging, NeoPixel, and STEMMA QT.
