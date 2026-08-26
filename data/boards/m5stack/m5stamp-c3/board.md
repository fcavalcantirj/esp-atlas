---
id: m5stamp-c3
type: board
brand: m5stack
name: Stamp-C3
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: m5-stamp
price_tier: cheap
dimensions_mm:
- 34.0
- 20.0
- 4.6
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_exposed: 13
  gpio_free: 9
notes:
- ESP32-C3; 4 MB flash
- SK6812 programmable RGB LED, 13 GPIO exposed, no onboard battery
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=13 QUOTED: vendor page states "IO Interfaces x13", pins G21,
  G20, G9, G18, G19, G1, G0, G10, G8, G7, G6, G5, G4'
- 'io.gpio_free=9 DERIVED, not quoted (SPEC-io-power.md §5.3). Exposed pads {G0,G1,G4,G5,G6,G7,G8,G9,G10,G18,G19,G20,G21}
  (13, quoted from vendor IO Interfaces list). Subtracting esp32-c3''s soc.reserved_pins
  that are exposed -- strapping {2,8,9}: {8,9} exposed (2), usb_flash_tied {18,19}:
  {18,19} exposed (2) -- gives 13 - 2 - 2 = 9.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Stamp_C3
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/Stamp_C3
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/Stamp_C3
  verified: '2026-08-26'
---

# Stamp-C3

34x20mm ESP32-C3 stamp module: USB-C, programmable RGB LED, 13 exposed GPIO.
