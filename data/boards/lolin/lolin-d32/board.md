---
id: lolin-d32
type: board
brand: lolin
name: LOLIN D32
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 57
- 25.4
usb:
  bridge: ch340
power:
  battery_connector: true
  charging: true
io:
  gpio_exposed: 22
notes:
- Espressif ESP32-WROOM-32 module, REV1; 4 MB flash
- Built-in LED on GPIO5
- Lithium battery interface, PH-2.0 2-pin connector, 500 mA max charging current,
  supports 3.7 V LiPo
- Physical USB connector shape not stated on the official page (omitted)
- 'Weight: 6.1 g'
- Plain ESP32-WROOM-32 module (single ordering code, no R-suffix) never had a PSRAM variant
- 'io.gpio_exposed=22 QUOTED: vendor page Technical specs table states "Digital
  I/O Pins | 22"; no enumerated GPIO pin-list/table is published (only partial
  Analog Input/Output pin numbers and LED_BUILTIN=GPIO5), so gpio_free is omitted.
  The 500 mA figure on this page is LiPo charging current, not a GPIO/rail output
  rating, so power_out is omitted'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/d32/d32.html
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-wroom-32_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/d32/d32.html
  verified: '2026-08-26'
---

# LOLIN D32

ESP32-WROOM-32 devkit with a LiPo battery/charging interface (PH-2.0, 500 mA max), CH340 USB-UART bridge, GPIO5 LED.
