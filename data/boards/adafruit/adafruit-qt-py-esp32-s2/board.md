---
id: adafruit-qt-py-esp32-s2
type: board
brand: adafruit
name: Adafruit QT Py ESP32-S2 WiFi Dev Board with STEMMA QT
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: qt-py
price_tier: cheap
dimensions_mm:
- 21.8
- 17.9
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 11
  gpio_free: 11
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 600
notes:
- 4 MB flash, 2 MB PSRAM
- Battery input pads on underside with diode protection for external packs up to 6V; no onboard charging circuit
- Same size, form factor, and pinout as Seeed Studio XIAO
- 'io.gpio_exposed=11 QUOTED: vendor page states "There are eleven GPIO pins broken
  out to pads."'
- 'io.power_out QUOTED: vendor page states "These pins are the output from the
  3.3V regulator, they can supply 600mA peak."'
- 'io.gpio_free=11 DERIVED: cross-referencing the vendor firmware repo''s own
  CircuitPython board pin-definition (pins.c) maps the eleven pads to GPIO5-9,
  16-18, 35-37 -- none of esp32-s2''s soc.reserved_pins (strapping 0/45/46,
  input_only 46, usb_flash_tied 19/20) are among them; the BOOT button (GPIO0)
  and the STEMMA QT connector''s dedicated I2C (SCL1/SDA1, GPIO40/41) and
  NeoPixel (GPIO38/39) sit off the eleven counted pads -- so 11 - 0 = 11'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5325
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s2/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s2/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_qtpy_esp32s2/pins.c
  verified: '2026-08-26'
---

# Adafruit QT Py ESP32-S2

Tiny ESP32-S2 board with native USB-C, STEMMA QT, RGB NeoPixel, and 4 MB flash / 2 MB PSRAM.
