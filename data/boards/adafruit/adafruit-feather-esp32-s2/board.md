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
  gpio_exposed: 20
  gpio_free: 20
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
- 'io.gpio_exposed=20 QUOTED: vendor pinouts page lists broken-out header pads D5,
  D6, D9, D10, D11, D12, D13 (7 digital), A0-A5 (6 analog, dual-named D8/D14-D18),
  SCK/MOSI/MISO (SPI), RX/TX (UART), SCL/SDA (I2C) = 20 GPIO-capable pads (RST/EN
  are control pins, not counted). io.gpio_free=20 DERIVED: cross-referencing the
  vendor firmware repo''s own CircuitPython board pin-definition (pins.c) maps
  every header pad to GPIO3-4, 5-6, 8-18, or 35-39 -- none of esp32-s2''s
  soc.reserved_pins (strapping 0/45/46, input_only 46, usb_flash_tied 19/20) are
  among the exposed pads, and NeoPixel/I2C_POWER/NEOPIXEL_POWER sit on
  GPIO21/33, off-header -- so 20 - 0 = 20'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5000
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-s2-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-esp32-s2-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_feather_esp32s2/pins.c
  verified: '2026-08-26'
---

# Adafruit ESP32-S2 Feather

Feather-form ESP32-S2 board with native USB-C, LiPoly JST charging, NeoPixel, and STEMMA QT.
