---
id: sparkfun-esp32-thing
type: board
brand: sparkfun
name: SparkFun ESP32 Thing
soc: esp32
flash_mb: 4
form_factor: devkit
price_tier: medium
dimensions_mm:
- 58.9
- 25.4
usb:
  connector: micro-usb
  bridge: ft231x
power:
  charging: true
notes:
- 4 MB flash
- 28 GPIO pins broken out; 10-electrode capacitive touch support
- 'Integrated LiPo battery charger confirmed on product page; battery connector presence not separately confirmed, so battery_connector is omitted'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-esp32-thing.html
  verified: '2026-08-22'
- field: usb
  url: https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide/all
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide/all
  verified: '2026-08-22'
---

# SparkFun ESP32 Thing

SparkFun's original ESP32 development board — a bare ESP32-WROOM devkit with Micro-USB (via an FTDI FT231x bridge), 4 MB flash, 28 broken-out GPIO pins, and an integrated LiPo charging circuit. Predates the Thing Plus (Feather-footprint) line.
