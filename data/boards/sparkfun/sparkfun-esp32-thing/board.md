---
id: sparkfun-esp32-thing
type: board
brand: sparkfun
name: SparkFun ESP32 Thing
soc: esp32
flash_mb: 4
psram_mb: 0
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
io:
  gpio_exposed: 28
  power_out:
    rail_v: [3.3]
    rail_ma_max: 600
notes:
- 4 MB flash
- 28 GPIO pins broken out; 10-electrode capacitive touch support
- 'Integrated LiPo battery charger confirmed on product page; battery connector presence not separately confirmed, so battery_connector is omitted'
- ESP32-D0WDQ6-V3 chip (per SparkFun's own board docs); this chip variant has no PSRAM per Espressif's ESP32 series ordering table
- 'io.gpio_exposed=28 QUOTED: vendor product page Features & Specs state "28 GPIO"'
- 'io.power_out QUOTED: vendor hookup guide states "The 3.3V regulator on the ESP32
  Thing can reliably supply up to 600mA"'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-esp32-thing.html
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32_datasheet_en.html
  verified: '2026-08-24'
- field: usb
  url: https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide/all
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide/all
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.sparkfun.com/sparkfun-esp32-thing.html
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide/all
  verified: '2026-08-26'
---

# SparkFun ESP32 Thing

SparkFun's original ESP32 development board — a bare ESP32-WROOM devkit with Micro-USB (via an FTDI FT231x bridge), 4 MB flash, 28 broken-out GPIO pins, and an integrated LiPo charging circuit. Predates the Thing Plus (Feather-footprint) line.
