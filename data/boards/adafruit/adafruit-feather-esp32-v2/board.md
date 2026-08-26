---
id: adafruit-feather-esp32-v2
type: board
brand: adafruit
name: Adafruit ESP32 Feather V2 (8MB Flash 2MB PSRAM)
soc: esp32
flash_mb: 8
psram_mb: 2
form_factor: feather
price_tier: medium
dimensions_mm:
- 52.3
- 22.8
usb:
  connector: usb-c
  bridge: ch9102f
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
io:
  gpio_free: 13
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 8 MB flash, 2 MB PSRAM
- 'CH9102F USB-UART bridge (upgraded from CP2102N as of May 2022)'
- STEMMA QT connector with switchable 3.3V power; mini NeoPixel; user button on pin 38
- 'io.gpio_free=13 DERIVED, not quoted (SPEC-io-power.md §5.3). Pinouts page gives
  explicit GPIO numbers for all 21 header pins (bottom row: GPIO26/25/34/39/36/4/5/19/21/7/8/37;
  top row: GPIO13/12/27/33/15/32/14/20/22). Subtracting esp32''s soc.reserved_pins
  that are exposed among those 21 -- strapping {5,12,15} (3), input_only {34,36,39}
  (3), usb_flash_tied {7,8} (2) -- gives 21 - 8 = 13. Math not vendor-stated; verify
  before treating as exact.'
- 'io.power_out QUOTED: vendor page states "The regulator can supply 500mA peak
  but half of that is drawn by the ESP32"'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5400
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://learn.adafruit.com/adafruit-esp32-feather-v2/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-feather-v2/pinouts
  verified: '2026-08-26'
---

# Adafruit ESP32 Feather V2

Feather-form ESP32 board with USB-C, CH9102F UART bridge, LiPoly charging, NeoPixel, and STEMMA QT.
