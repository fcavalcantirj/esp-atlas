---
id: beetle-esp32-c3
type: board
brand: dfrobot
name: DFRobot Beetle ESP32-C3
soc: esp32-c3
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
io:
  gpio_exposed: 13
notes:
- 4 MB flash
- TP4057 Li-ion charge management chip, max 400 mA
- Ships with a GDI expansion board for display connectivity
- 13 digital I/O ports
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=13 QUOTED: vendor page states "It features 13 digital I/O ports"
  and "Digital I/O | x13"'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0868/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr0868/
  verified: '2026-08-26'
---

# DFRobot Beetle ESP32-C3

Coin-sized ESP32-C3 RISC-V board (25 x 20.5 mm): USB-C, 4 MB flash, onboard Li-ion charging, and a bundled GDI expansion board for displays.
