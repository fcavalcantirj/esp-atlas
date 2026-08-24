---
id: firebeetle-esp32
type: board
brand: dfrobot
name: DFRobot FireBeetle ESP32
soc: esp32
flash_mb: 16
psram_mb: 0
form_factor: firebeetle
price_tier: cheap
dimensions_mm:
- 29
- 58
usb:
  bridge: ch340
power:
  battery_connector: true
  charging: true
extras:
- sd-card
notes:
- 16 MB flash, 520 KB SRAM
- CH340 USB-to-serial bridge (driver install required)
- Onboard microSD slot
- Dual-Core ESP-WROOM-32 module
- ESP32-WROOM-32/32D/32U modules only ever shipped in non-PSRAM ordering codes (no R-suffix variant exists in Espressif's datasheets)
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0478/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-wroom-32d_esp32-wroom-32u_datasheet_en.html
  verified: '2026-08-24'
---

# DFRobot FireBeetle ESP32

Original low-power FireBeetle main board on the ESP-WROOM-32 module: 16 MB flash, CH340 USB-serial bridge, onboard microSD slot, and Li-ion battery charging.
