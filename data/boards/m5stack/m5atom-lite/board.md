---
id: m5atom-lite
type: board
brand: m5stack
name: Atom-Lite
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: m5-atom
price_tier: cheap
dimensions_mm:
- 24.0
- 24.0
- 9.5
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_exposed: 6
  gpio_free: 6
notes:
- ESP32-PICO-D4; 4 MB flash
- SK6812 3535 programmable RGB LED, IR transmitter, customizable button, 2.4G 3D
  antenna, Grove/HY2.0 expansion, no onboard battery
- ESP32-PICO-D4 is a SiP module with only in-package flash; it has no integrated PSRAM (only pins to attach external PSRAM, unused here)
- 'io.gpio_exposed=6 QUOTED: vendor Specifications table states "PIN Interface:
  G19, G21, G22, G23, G25, G33"'
- 'io.gpio_free=6 DERIVED, not quoted (SPEC-io-power.md §5.3). Exposed pads {G19,G21,G22,G23,G25,G33}
  (6, quoted from vendor PIN Interface spec row). Subtracting esp32''s soc.reserved_pins
  that are exposed -- strapping {0,2,5,12,15} (0 exposed), input_only {34,35,36,39}
  (0 exposed), usb_flash_tied {6,7,8,9,10,11} (0 exposed) -- gives 6 - 0 - 0 - 0
  = 6.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/ATOM%20Lite
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-pico_series_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/ATOM%20Lite
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/ATOM%20Lite
  verified: '2026-08-26'
---

# Atom-Lite

24x24mm ESP32-PICO atom unit: programmable RGB LED, IR transmitter, Grove port, USB-C.
