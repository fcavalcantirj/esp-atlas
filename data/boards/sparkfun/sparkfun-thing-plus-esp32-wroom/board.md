---
id: sparkfun-thing-plus-esp32-wroom
type: board
brand: sparkfun
name: SparkFun Thing Plus - ESP32 WROOM (USB-C)
soc: esp32
form_factor: thing-plus
price_tier: medium
dimensions_mm:
- 64.77
- 22.86
usb:
  connector: usb-c
  bridge: ch340
power:
  battery_connector: true
  charging: true
extras:
- qwiic
- sd-card
- rgb-led
notes:
- ESP32-WROOM-32E module; 16 MB flash
- Battery charging via onboard MCP73831 linear charge management controller (500mA max), JST connector for single-cell LiPo
- Onboard MAX17048 LiPo fuel gauge for battery-level monitoring
- Thing Plus form factor is pin-compatible with the Adafruit Feather footprint
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-thing-plus-esp32-wroom-usb-c.html
  verified: '2026-08-22'
- field: usb.bridge
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-22'
- field: power
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-22'
---

# SparkFun Thing Plus - ESP32 WROOM (USB-C)

Feather-footprint-compatible ESP32-WROOM-32E board with USB-C, a microSD slot, Qwiic connector, and onboard LiPo charging with a fuel gauge. This is the current USB-C revision of SparkFun's Thing Plus ESP32 line; the earlier "ESP32 Thing Plus C" SKU (WRL-20168's predecessor) was retired in favor of this listing and is not tracked as a separate board.
