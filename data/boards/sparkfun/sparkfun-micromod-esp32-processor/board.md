---
id: sparkfun-micromod-esp32-processor
type: board
brand: sparkfun
name: SparkFun MicroMod ESP32 Processor
soc: esp32
flash_mb: 16
psram_mb: 0
form_factor: micromod
price_tier: cheap
dimensions_mm:
- 22.0
- 22.0
usb:
  connector: none
io:
  gpio_exposed: 13
notes:
- ESP32-D0WDQ6-V3; 16 MB flash
- ESP32-D0WDQ6-V3 chip variant has no PSRAM per Espressif's ESP32 series ordering table
- M.2-style MicroMod edge connector; requires a MicroMod carrier board (not sold with one). USB is routed through MicroMod connector pads to the carrier board rather than exposed on the processor board itself
- Onboard status LED and 2.4GHz WiFi/BLE antenna
- 'io.gpio_exposed=13 QUOTED: vendor hookup guide states "The MicroMod connector
  supports a total of 12 general purpose IO pins, 7 of which are used on the ESP32
  Processor, on top of the 6 dedicated pins" -- 7 general-purpose + 6 dedicated
  = 13, summing the two vendor-stated integers directly (no estimation)'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-micromod-esp32-processor.html
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/micromod-esp32-processor-board-hookup-guide/all
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://learn.sparkfun.com/tutorials/micromod-esp32-processor-board-hookup-guide/hardware-overview
  verified: '2026-08-26'
---

# SparkFun MicroMod ESP32 Processor

An ESP32-D0WDQ6-V3 processor board in SparkFun's MicroMod form factor: a small M.2-keyed edge-connector module meant to plug into a MicroMod carrier board rather than be used standalone. 16 MB flash, dual-core LX6 up to 240MHz, WiFi + Bluetooth.
