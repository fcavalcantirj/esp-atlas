---
id: adafruit-itsybitsy-esp32
type: board
brand: adafruit
name: Adafruit ItsyBitsy ESP32 - PCB Antenna (8MB Flash 2MB PSRAM)
soc: esp32
flash_mb: 8
psram_mb: 2
form_factor: itsybitsy
price_tier: cheap
dimensions_mm:
- 36.0
- 17.6
usb:
  connector: micro-usb
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 20
  gpio_free: 14
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 8 MB flash, 2 MB PSRAM
- Built-in USB-to-serial converter with auto-reset over Micro USB; bridge chip model not named on the product page (omitted)
- Battery input pads on underside with diode protection for external packs up to 6V; no onboard charging circuit
- 'io.gpio_exposed=20 QUOTED: vendor page states "The ItsyBitsy ESP32 has 20 general
  purpose ''IO'' pins."'
- 'io.gpio_free=14 DERIVED, not quoted (SPEC-io-power.md §5.3). Pinouts page gives
  explicit GPIO numbers for all 20 header pins (bottom row: GPIO25/26/4/38/37/36/19/21/22;
  top row: GPIO13/12/14/33/32/7/5/27/15/20/8). Subtracting esp32''s soc.reserved_pins
  that are exposed among those 20 -- strapping {5,12,15} (3), input_only {36} (1),
  usb_flash_tied {7,8} (2) -- gives 20 - 6 = 14. Math not vendor-stated; verify
  before treating as exact.'
- 'io.power_out QUOTED: vendor page states "You can draw 500mA whether powered
  by USB or battery."'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5889
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-itsybitsy-esp32/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://learn.adafruit.com/adafruit-itsybitsy-esp32/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-itsybitsy-esp32/pinouts
  verified: '2026-08-26'
---

# Adafruit ItsyBitsy ESP32

Small-form ESP32 board with Micro USB, RGB NeoPixel, STEMMA QT, and 8 MB flash / 2 MB PSRAM.
