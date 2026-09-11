---
id: adafruit-huzzah32-esp32-feather
type: board
brand: adafruit
name: Adafruit HUZZAH32 – ESP32 Feather Board
aka:
- featheresp32
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: feather
price_tier: cheap
dimensions_mm:
- 50.0
- 23.0
usb:
  connector: micro-usb
power:
  battery_connector: true
  charging: true
extras:
- pcb-antenna
io:
  gpio_free: 9
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 4 MB flash; no PSRAM
- Integrated LiPoly charger with JST 2-PH battery connector; battery and cable sold
  separately
- Built-in USB-to-Serial converter over Micro USB; bridge chip model not named on
  the product page (omitted)
- io.gpio_free=9 DERIVED, not quoted (SPEC-io-power.md §5.3). Pinouts page states
  explicit GPIO numbers for 14 header pins (bottom row A0-A5 = GPIO26/25/34/39/36/4
  plus GPIO21; top row = GPIO13/12/27/33/15/32/14); RX/TX/SCL/SDA are also broken
  out on the header but the page never restates their GPIO numbers, so they are excluded
  from this count rather than guessed. Subtracting esp32's soc.reserved_pins that
  are exposed among those 14 -- strapping {12,15} (2), input_only {34,36,39} (3) --
  gives 14 - 5 = 9. Math not vendor-stated; verify before treating as exact.
- 'io.power_out QUOTED: vendor page states "The regulator can supply 500mA peak but
  half of that is drawn by the ESP32"'
download_mode:
  mode: auto
getting_started: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather
images:
  photo: https://cdn-learn.adafruit.com/guides/images/000/001/641/medium800/thumb.jpg
usb_serial: other
sources:
- field: '*'
  url: https://www.adafruit.com/product/3591
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather/pinouts
  verified: '2026-08-26'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/featheresp32.json
  verified: '2026-09-07'
- field: download_mode
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather
  verified: '2026-09-11'
- field: images
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather
  verified: '2026-09-11'
- field: usb_serial
  url: https://learn.adafruit.com/adafruit-huzzah32-esp32-feather
  verified: '2026-09-11'
---

# Adafruit HUZZAH32 – ESP32 Feather Board

Feather-form ESP32 board with Micro USB, integrated LiPoly charging via JST connector, and 4 MB flash.
