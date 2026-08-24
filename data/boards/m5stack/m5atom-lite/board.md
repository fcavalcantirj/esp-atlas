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
notes:
- ESP32-PICO-D4; 4 MB flash
- SK6812 3535 programmable RGB LED, IR transmitter, customizable button, 2.4G 3D
  antenna, Grove/HY2.0 expansion, no onboard battery
- ESP32-PICO-D4 is a SiP module with only in-package flash; it has no integrated PSRAM (only pins to attach external PSRAM, unused here)
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/ATOM%20Lite
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-pico_series_datasheet_en.html
  verified: '2026-08-24'
---

# Atom-Lite

24x24mm ESP32-PICO atom unit: programmable RGB LED, IR transmitter, Grove port, USB-C.
