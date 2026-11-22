---
id: adafruit-feather-esp32-s3-no-psram
type: board
brand: adafruit
name: Adafruit ESP32-S3 Feather (8MB Flash No PSRAM)
aka:
- ADAFRUIT_FEATHER_ESP32S3_NOPSRAM
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: feather
price_tier: medium
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
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
- '8 MB flash, no PSRAM (vendor: "comes with 8 MByte of Flash, no PSRAM" plus 512KB
  of SRAM)'
- LiPoly battery with built-in USB-C charging; MAX17048 battery monitor
- NeoPixel with pin-controlled power; STEMMA QT connector for I2C; Reset and DFU (BOOT0)
  buttons; On/Charge/User LEDs
- 'io.power_out QUOTED: vendor pinouts page states "These pins are the output from
  the 3.3V regulator, they can supply 500mA peak." (shared ESP32-S3 Feather guide)'
- usb_serial derived from usb.bridge (native) + soc usb.type otg-full-speed + serial-jtag
- 'dimensions_mm OMITTED: no board dimensions stated on the product page'
- 'io.gpio_exposed/gpio_free OMITTED: vendor pinouts page does not print an explicit
  broken-out GPIO count, so no count is derived'
getting_started: https://learn.adafruit.com/adafruit-esp32-s3-feather
images:
  pinout: https://cdn-learn.adafruit.com/assets/assets/000/139/614/medium800/adafruit_products_Artboard_1_4x.png?1757533230
platformio_definitions:
- id: adafruit_feather_esp32s3_nopsram
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: d886439401aefac4265208496607e13385f2f002810f608da4c8749471022683
- id: adafruit_feather_esp32s3_nopsram
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 7702a234b4f4b35728ff169db0d419a717896ea23ecd5d064740f76ddf01901d
sources:
- field: '*'
  url: https://www.adafruit.com/product/5323
  verified: '2026-09-11'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts
  verified: '2026-09-11'
- field: usb_serial
  url: https://www.adafruit.com/product/5323
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-esp32-s3-feather
  verified: '2026-09-11'
- field: images.pinout
  url: https://cdn-learn.adafruit.com/assets/assets/000/139/614/medium800/adafruit_products_Artboard_1_4x.png?1757533230
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/adafruit_feather_esp32s3_nopsram.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/adafruit_feather_esp32s3_nopsram.json
  verified: '2026-11-22'
---

# Adafruit ESP32-S3 Feather (No PSRAM)

Feather-form ESP32-S3 board with 8 MB flash and no PSRAM: native USB-C, LiPoly JST charging with MAX17048 monitor, NeoPixel, and STEMMA QT.
