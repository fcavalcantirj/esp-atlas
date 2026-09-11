---
id: adafruit-qt-py-esp32
type: board
brand: adafruit
name: Adafruit QT Py ESP32 Pico
aka:
- adafruit_qtpy_esp32_pico
soc: esp32
flash_mb: 8
psram_mb: 2
form_factor: qt-py
price_tier: cheap
usb:
  connector: usb-c
  bridge: cp2102n-or-ch9102f
usb_serial: usb-uart-bridge-unspecified
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 11
notes:
- 8 MB flash, 2 MB PSRAM on the ESP32 PICO-D4 module
- 'flash_mb=8 QUOTED: guide states "8 MB of Flash memory". psram_mb=2 QUOTED: guide
  states "2 MB of PSRAM".'
- 'Battery input pads on underside with diode protection for external packs up to
  6V; no onboard charging. QUOTED: "Battery input pads on underside with diode
  protection for external battery packs up to 6V input".'
- 'usb.bridge/usb_serial: this plain-ESP32 board has no native USB, so it flashes
  over a USB-serial bridge; the pinouts page documents two production variants --
  QUOTED "The CH9102F USB to serial converter can handle 50bps to 4Mbps max rate."
  and "The CP2102N USB to serial converter can handle 3 mbps max rate." Because the
  fitted chip varies by run, usb_serial is recorded as usb-uart-bridge-unspecified.'
- 'io.gpio_exposed=11 QUOTED: pinouts page states "There are eleven GPIO pins
  broken out to pads." (gpio_free omitted -- no vendor-printed free count and not
  derived here).'
- 'extras QUOTED: "Built-in RGB NeoPixel LED with power control" and "STEMMA QT
  plug-n-play connector".'
getting_started: https://learn.adafruit.com/adafruit-qt-py-esp32-pico
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-pico
  verified: '2026-09-11'
- field: usb_serial
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-pico/pinouts
  verified: '2026-09-11'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-pico/pinouts
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-pico
  verified: '2026-09-11'
---

# Adafruit QT Py ESP32 Pico

QT Py-form ESP32 PICO-D4 board with USB-C, STEMMA QT, RGB NeoPixel, and 8 MB flash / 2 MB PSRAM.
