---
id: adafruit-feather-esp32-s2-reverse-tft
type: board
brand: adafruit
name: Adafruit ESP32-S2 Reverse TFT Feather (4MB Flash 2MB PSRAM)
aka:
- ADAFRUIT_FEATHER_ESP32S2_REVTFT
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
- 'Color 1.14" IPS TFT, 240x135 pixels, ST7789 chipset, mounted on the reverse (button)
  side of the board'
- LiPoly battery with built-in USB-C charging; LC709203 I2C battery monitor
- Three user tactile buttons (D0 -- also BOOT, D1, D2); NeoPixel with pin-controlled
  power; STEMMA QT connector with switchable power; On/Charge/User LEDs
- 'io.power_out QUOTED: vendor pinouts page states "These pins are the output from
  the 3.3V regulator, they can supply 500mA peak."'
- 'usb_serial OMITTED: soc esp32-s2 usb.type is otg-full-speed with no serial-JTAG
  peripheral, so there is no native-usb-serial-jtag path (matches sibling adafruit-feather-esp32-s2)'
- 'dimensions_mm OMITTED: no board dimensions stated on the vendor overview or pinouts
  pages'
- 'io.gpio_exposed/gpio_free OMITTED: vendor pinouts page does not print an explicit
  broken-out GPIO count, so no count is derived'
getting_started: https://learn.adafruit.com/esp32-s2-reverse-tft-feather
sources:
- field: '*'
  url: https://www.adafruit.com/product/5345
  verified: '2026-09-11'
- field: '*'
  url: https://learn.adafruit.com/esp32-s2-reverse-tft-feather/overview
  verified: '2026-09-11'
- field: io.power_out
  url: https://learn.adafruit.com/esp32-s2-reverse-tft-feather/pinouts
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/esp32-s2-reverse-tft-feather
  verified: '2026-09-11'
---

# Adafruit ESP32-S2 Reverse TFT Feather

Feather-form ESP32-S2 board with a reverse-mounted 1.14in 240x135 IPS display and three user buttons, native USB-C, LiPoly charging, NeoPixel, and STEMMA QT.
