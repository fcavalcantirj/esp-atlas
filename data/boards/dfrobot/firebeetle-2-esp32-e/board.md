---
id: firebeetle-2-esp32-e
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-E
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: firebeetle
price_tier: cheap
dimensions_mm:
- 25.4
- 60
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- sd-card
notes:
- 4 MB flash
- ESP32-WROOM-32E module, 520 KB SRAM
- PH2.0 connector for 3.7 V Li-ion, onboard charging circuit
- GDI display connector onboard
- DFRobot sells a separate "FireBeetle 2 ESP32-E (N16R2)" SKU (DFR1139) specifically to add PSRAM, confirming this base DFR0654 board (whose own spec page never mentions PSRAM) uses the non-R2 ESP32-WROOM-32E ordering code with no PSRAM
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0654/
  verified: '2026-08-22'
- field: psram_mb
  url: https://wiki.dfrobot.com/dfr1139/
  verified: '2026-08-24'
---

# DFRobot FireBeetle 2 ESP32-E

Low-power IoT main board on the ESP-WROOM-32E module: 4 MB flash, USB-C, onboard Li-ion charging via PH2.0 connector, WS2812 RGB LED, and a microSD slot.
