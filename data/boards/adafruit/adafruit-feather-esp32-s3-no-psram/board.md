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
---

# Adafruit ESP32-S3 Feather (No PSRAM)

Feather-form ESP32-S3 board with 8 MB flash and no PSRAM: native USB-C, LiPoly JST charging with MAX17048 monitor, NeoPixel, and STEMMA QT.
