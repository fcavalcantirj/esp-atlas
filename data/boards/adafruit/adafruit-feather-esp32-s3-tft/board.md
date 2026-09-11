---
id: adafruit-feather-esp32-s3-tft
type: board
brand: adafruit
name: Adafruit ESP32-S3 TFT Feather (4MB Flash 2MB PSRAM)
aka:
- ADAFRUIT_FEATHER_ESP32S3_TFT
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: feather
price_tier: medium
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
display: 1.14in 240x135 IPS ST7789
extras:
- rgb-led
- stemma-qt
io:
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- '4 MB flash, 2 MB PSRAM (vendor: "4 MByte of Flash and 2 MByte of PSRAM")'
- 'Front-mounted color 1.14" IPS TFT, 240x135 pixels, ST7789 chipset'
- LiPoly battery with built-in USB-C charging; battery monitor is either the LC709203
  (prior to March 2023) or the MAX17048 (after March 6, 2023)
- NeoPixel with pin-controlled power; STEMMA QT connector with switchable power; Reset
  and DFU (BOOT0) buttons; On/Charge/User LEDs
- 'io.power_out QUOTED: vendor pinouts page states "3.3V - These pins are the output
  from the 3.3V regulator, they can supply 500mA peak."'
- usb_serial derived from usb.bridge (native) + soc usb.type otg-full-speed + serial-jtag
- 'dimensions_mm OMITTED: no board dimensions stated on the vendor overview or pinouts
  pages'
- 'io.gpio_exposed/gpio_free OMITTED: vendor pinouts page does not print an explicit
  broken-out GPIO count, so no count is derived'
getting_started: https://learn.adafruit.com/adafruit-esp32-s3-tft-feather
sources:
- field: '*'
  url: https://www.adafruit.com/product/5483
  verified: '2026-09-11'
- field: '*'
  url: https://learn.adafruit.com/adafruit-esp32-s3-tft-feather/overview
  verified: '2026-09-11'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s3-tft-feather/pinouts
  verified: '2026-09-11'
- field: usb_serial
  url: https://www.adafruit.com/product/5483
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-esp32-s3-tft-feather
  verified: '2026-09-11'
---

# Adafruit ESP32-S3 TFT Feather

Feather-form ESP32-S3 board with a front-mounted 1.14in 240x135 IPS display, native USB-C, LiPoly charging, NeoPixel, and STEMMA QT.
