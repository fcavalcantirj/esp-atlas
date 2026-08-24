---
id: sparkfun-iot-redboard-esp32
type: board
brand: sparkfun
name: SparkFun IoT RedBoard - ESP32 Development Board
soc: esp32
psram_mb: 0
form_factor: devkit
price_tier: medium
dimensions_mm:
- 58.4
- 68.6
usb:
  connector: usb-c
  bridge: ch340g
power:
  battery_connector: true
  charging: true
extras:
- qwiic
- sd-card
- rgb-led
notes:
- ESP32-D0WD-V3; module flash configurable at 4/8/16 MB per product page (default shipped capacity not stated)
- Battery charging via onboard MCP73831 (500mA default), JST connector for single-cell LiPo; onboard MAX17048 fuel gauge
- Arduino Uno-compatible form factor ("RedBoard" line) with Qwiic connector and microSD slot
- ESP32-D0WD-V3 chip variant has no PSRAM per Espressif's ESP32 series ordering table
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-iot-redboard-esp32-development-board.html
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/iot-redboard-esp32-development-board-hookup-guide/all
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32_datasheet_en.html
  verified: '2026-08-24'
---

# SparkFun IoT RedBoard - ESP32 Development Board

An Arduino Uno-shaped ESP32 devkit in SparkFun's RedBoard line, with USB-C (CH340G bridge), Qwiic connector, microSD slot, addressable RGB status LED, and onboard LiPo charging with fuel gauge.
