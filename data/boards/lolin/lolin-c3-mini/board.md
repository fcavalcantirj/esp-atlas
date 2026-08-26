---
id: lolin-c3-mini
type: board
brand: lolin
name: LOLIN C3 mini
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: lolin-mini
price_tier: cheap
dimensions_mm:
- 34.3
- 25.4
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_exposed: 12
notes:
- Based on ESP32-C3, RISC-V single-core Wi-Fi + Bluetooth LE
- 4 MB flash
- 12x digital I/O pins
- Onboard WS2812B addressable RGB LED
- 'Weight: 2.6 g'
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=12 QUOTED: vendor page states "12x IO" (Features) and "Digital
  I/O Pins | 12" (Technical specs table); no enumerated GPIO pin-list/table is
  published, so gpio_free and power_out are omitted'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/c3/c3_mini.html
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/c3/c3_mini.html
  verified: '2026-08-26'
---

# LOLIN C3 mini

Thumb-sized bare-C3 board: RISC-V ESP32-C3, 4 MB flash, USB-C, onboard WS2812B RGB LED, 12 IO.
