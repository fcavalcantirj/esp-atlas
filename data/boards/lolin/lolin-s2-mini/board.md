---
id: lolin-s2-mini
type: board
brand: lolin
name: LOLIN S2 mini
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: lolin-mini
price_tier: cheap
dimensions_mm:
- 34.3
- 25.4
usb:
  connector: usb-c
io:
  gpio_exposed: 27
notes:
- Based on ESP32-S2FN4R2; 4 MB flash, 2 MB PSRAM
- 27x digital I/O pins
- Pin-compatible with LOLIN D1 mini shields
- 'io.gpio_exposed=27 QUOTED: vendor page states "27x IO" (Features) and "Digital
  I/O Pins | 27" (Technical specs table); no enumerated GPIO pin-list/table is
  published, so gpio_free and power_out are omitted'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/s2/s2_mini.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/s2/s2_mini.html
  verified: '2026-08-26'
---

# LOLIN S2 mini

Thumb-sized bare-S2 board: ESP32-S2FN4R2 (4 MB flash, 2 MB PSRAM), USB-C, 27 IO, D1-mini-shield compatible footprint.
