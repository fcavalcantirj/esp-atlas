---
id: beetle-esp32-c6
type: board
brand: dfrobot
name: DFRobot Beetle ESP32-C6
soc: esp32-c6
flash_mb: 4
psram_mb: 0
form_factor: beetle
price_tier: cheap
dimensions_mm:
- 25
- 20.5
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
notes:
- 4 MB flash
- TP4057 Li-ion charge management chip, max 0.5 A
- 13 digital I/O ports in a coin-sized form factor
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr1117/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
---

# DFRobot Beetle ESP32-C6

Coin-sized ESP32-C6 board (25 x 20.5 mm) for wearable and smart-home IoT: USB-C, 4 MB flash, onboard Li-ion charging, and 13 digital I/O ports.
