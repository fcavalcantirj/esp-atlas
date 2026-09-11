---
id: adafruit-metro-esp32-s2
type: board
brand: adafruit
name: Adafruit Metro ESP32-S2
aka:
- adafruit_metro_esp32s2
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: metro
price_tier: medium
dimensions_mm:
- 53.2
- 72
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
notes:
- 4 MB flash, 2 MB PSRAM on the ESP32-S2.
- 'flash_mb=4 QUOTED: "4 MByte of Flash". psram_mb=2 QUOTED: "2 MByte of PSRAM".'
- 'dimensions_mm QUOTED: "53.2mm x 72mm / 2" x 2.8""; barrel-jack height 14.8 mm
  omitted (two-axis footprint recorded).'
- 'usb.connector=usb-c / bridge=native QUOTED: "USB type C" and "native USB".
  usb_serial omitted: esp32-s2 has USB-OTG only (no USB-Serial-JTAG peripheral).'
- 'power QUOTED: "Lipoly battery" connector and "Built-in battery charging when
  powered over DC or USB".'
- 'extras QUOTED: "status NeoPixel" and "STEMMA QT connector for I2C devices".'
- 'io omitted: the product page prints no explicit broken-out GPIO count.'
getting_started: https://learn.adafruit.com/adafruit-metro-esp32-s2
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-metro-esp32-s2
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-metro-esp32-s2
  verified: '2026-09-11'
---

# Adafruit Metro ESP32-S2

Arduino-Uno-form-factor ESP32-S2 board with native USB-C, 4 MB flash / 2 MB PSRAM, LiPoly charging, and STEMMA QT.
