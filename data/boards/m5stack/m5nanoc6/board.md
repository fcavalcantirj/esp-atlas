---
id: m5nanoc6
type: board
brand: m5stack
name: NanoC6
soc: esp32-c6
flash_mb: 4
psram_mb: 0
form_factor: m5-nano
price_tier: cheap
dimensions_mm:
- 23.5
- 12.0
- 9.5
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_free: 2
  power_out:
    rail_v:
    - 5
    rail_ma_max: 600
notes:
- ESP32-C6FH4; 4 MB flash
- WS2812 programmable RGB LED, IR transmitter, button on GPIO9, Grove interface,
  ceramic antenna, no onboard battery
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.power_out QUOTED: vendor page states "Grove Maximum Output Current: DC 5V@600mA
  (depends on USB supply)"'
- 'io.gpio_free=2 DERIVED, not quoted (SPEC-io-power.md §5.3). The vendor pinmap
  page states only one user-facing expansion connector, the HY2.0-4P Grove port
  (G2, G1) -- the other named pins (G3/G20 IR, G19 RGB+EN, G9 button, G7 LED) are
  hard-consumed by onboard peripherals, not free header pins. Subtracting esp32-c6''s
  soc.reserved_pins that are exposed on the Grove pair -- strapping {8,9,10,11,15}
  and usb_flash_tied {12,13}, neither of which is G1 or G2 -- leaves both pads free:
  2 - 0 = 2. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/M5NanoC6
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
- field: io.power_out
  url: https://docs.m5stack.com/en/core/M5NanoC6
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/M5NanoC6
  verified: '2026-08-26'
---

# NanoC6

23.5x12mm ESP32-C6 nano unit: programmable RGB LED, IR transmitter, Grove port, USB-C.
