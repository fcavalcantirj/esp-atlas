---
id: firebeetle-2-esp32-s3
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: firebeetle
price_tier: medium
dimensions_mm:
- 25.4
- 60
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- camera
io:
  gpio_exposed: 26
notes:
- 16 MB flash, 8 MB PSRAM (ESP32-S3-WROOM-1-N16R8)
- Onboard OV2640 camera (2 MP, 68° FOV) with independent power circuit
- GDI display connector onboard
- ETA6003 Li-ion charge management, max 1 A
- 'io.gpio_exposed=26 QUOTED: vendor page states "Digital I/O x26"'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0975
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr0975
  verified: '2026-08-26'
---

# DFRobot FireBeetle 2 ESP32-S3

AI-oriented ESP32-S3 board with 16 MB flash, 8 MB PSRAM, an onboard OV2640 camera, USB-C, and a GDI display connector for AIoT and image-recognition projects.
