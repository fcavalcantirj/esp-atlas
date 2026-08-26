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
  gpio_free: 10
notes:
- Based on ESP32-C3, RISC-V single-core Wi-Fi + Bluetooth LE
- 4 MB flash
- 12x digital I/O pins
- Onboard WS2812B addressable RGB LED
- 'Weight: 2.6 g'
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=12 QUOTED: vendor page states "12x IO" (Features) and "Digital
  I/O Pins | 12" (Technical specs table); no enumerated GPIO pin-list/table is
  published in the spec table, so power_out is omitted'
- 'io.gpio_free=10 DERIVED: the vendor''s own labeled pinout diagram (c3_mini_v2.1.0
  silkscreen photo) enumerates exactly 12 header GPIO pads: TX/21, RX/20, 10, 8,
  7, 6, A3/3, A2/2, A1/1, A0/0, A4/4, A5/5 -- matching the "12x IO" spec exactly.
  Of esp32-c3''s soc.reserved_pins, strapping GPIO2 and GPIO8 are among them (2
  pins); usb_flash_tied GPIO18/19 are not exposed; ESP32-C3 has no PSRAM to
  consume a pin. GPIO7 doubles as the onboard WS2812 RGB LED but remains header-exposed
  so it is not subtracted -- so 12 - 2 = 10'
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
- field: io.gpio_free
  url: https://www.wemos.cc/en/latest/_images/c3_mini_v2.1.0_2_16x16.jpg
  verified: '2026-08-26'
---

# LOLIN C3 mini

Thumb-sized bare-C3 board: RISC-V ESP32-C3, 4 MB flash, USB-C, onboard WS2812B RGB LED, 12 IO.
