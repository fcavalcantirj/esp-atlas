---
id: firebeetle-2-esp32-c6
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-C6
soc: esp32-c6
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
io:
  gpio_exposed: 19
notes:
- 4 MB flash
- Supports 5 V solar panel charging via CN3165 MPPT chip, max 0.5 A
- GDI display connector onboard
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=19 QUOTED: vendor page states "Digital I/O: x19"'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr1075/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr1075/
  verified: '2026-08-26'
---

# DFRobot FireBeetle 2 ESP32-C6

Low-power ESP32-C6 IoT board for smart-home control: 4 MB flash, USB-C, Li-ion charging plus 5 V solar/MPPT input, and a GDI display connector.
