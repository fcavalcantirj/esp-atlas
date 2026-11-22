---
id: adafruit-feather-esp32-s2-tft
type: board
brand: adafruit
name: Adafruit ESP32-S2 TFT Feather (4MB Flash 2MB PSRAM)
aka:
- ADAFRUIT_FEATHER_ESP32S2_TFT
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: feather
price_tier: medium
usb:
  connector: usb-c
  bridge: native
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
- 4 MB flash, 2 MB PSRAM
- 'Front-mounted color 1.14" IPS TFT, 240x135 pixels, ST7789 chipset (vendor: "bright
  and colorful display with ST7789 chipset that can be viewed at any angle")'
- LiPoly battery with built-in USB-C charging; LC709203 I2C battery monitor
- NeoPixel with pin-controlled power; STEMMA QT connector with switchable power; Reset
  and DFU (BOOT0) buttons; On/Charge/User LEDs
- 'io.power_out QUOTED: vendor pinouts page states "These pins are the output from
  the 3.3V regulator, they can supply 500mA peak."'
- 'usb_serial OMITTED: soc esp32-s2 usb.type is otg-full-speed with no serial-JTAG
  peripheral, so there is no native-usb-serial-jtag path (matches sibling adafruit-feather-esp32-s2)'
- 'dimensions_mm OMITTED: no board dimensions stated on the vendor overview or pinouts
  pages'
- 'io.gpio_exposed/gpio_free OMITTED: vendor pinouts page does not print an explicit
  broken-out GPIO count, so no count is derived'
getting_started: https://learn.adafruit.com/adafruit-esp32-s2-tft-feather
images:
  pinout: https://cdn-learn.adafruit.com/assets/assets/000/109/051/medium800/adafruit_products_Adafruit_ESP32-S2_TFT_Feather_Pinout.png?1645048115
platformio_definitions:
- id: adafruit_feather_esp32s2_tft
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 52659a0c6d1a232b0d09084626ef71d15aad39db634963284d09969f852d4fe3
- id: adafruit_feather_esp32s2_tft
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 3caed4903c1ed12263d06c6d3797a153f0a19025cf166124d9f2f1544cc571c5
sources:
- field: '*'
  url: https://www.adafruit.com/product/5300
  verified: '2026-09-11'
- field: '*'
  url: https://learn.adafruit.com/adafruit-esp32-s2-tft-feather/overview
  verified: '2026-09-11'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s2-tft-feather/pinouts
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-esp32-s2-tft-feather
  verified: '2026-09-11'
- field: images.pinout
  url: https://cdn-learn.adafruit.com/assets/assets/000/109/051/medium800/adafruit_products_Adafruit_ESP32-S2_TFT_Feather_Pinout.png?1645048115
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/adafruit_feather_esp32s2_tft.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/adafruit_feather_esp32s2_tft.json
  verified: '2026-11-22'
---

# Adafruit ESP32-S2 TFT Feather

Feather-form ESP32-S2 board with a front-mounted 1.14in 240x135 IPS display, native USB-C, LiPoly charging, NeoPixel, and STEMMA QT.
