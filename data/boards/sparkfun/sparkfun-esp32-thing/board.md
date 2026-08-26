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
  gpio_free: 17
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
- 'io.gpio_free=17 DERIVED: the vendor''s own graphical datasheet enumerates all
  28 header pads by GPIO number (36,37,38,39,32,33,34,35,25,26,27,14,12,13 on
  the left header; 21,1,3,22,19,23,18,5,15,2,0,4,17,16 on the right), matching
  the vendor''s own "28 GPIO" count exactly. This is the bare ESP32-D0WDQ6-V3
  chip (not a WROOM/WROVER module), so GPIO37/38 are physically routed and the
  datasheet''s own legend marks GPIO36/37/38/39 all with "*GPIO: Port Input
  Only" -- two more input-only pins than esp32''s soc.reserved_pins (34/35/36/39),
  which is scoped to the common WROOM module that does not break out 37/38. Of
  esp32''s soc.reserved_pins, strapping 0/2/5/12/15 are all exposed (5 pins);
  input_only 34/35/36/39 are exposed (4 pins); usb_flash_tied 6/7/8 are not on
  the header. 28 total pads - 5 strapping - 4 input-only - 2 vendor-confirmed
  extra input-only (37, 38) = 17'
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
- field: io.gpio_free
  url: https://cdn.sparkfun.com/assets/learn_tutorials/5/0/7/ESP32ThingV1a.pdf
  verified: '2026-08-26'
---

# SparkFun ESP32 Thing

SparkFun's original ESP32 development board — a bare ESP32-WROOM devkit with Micro-USB (via an FTDI FT231x bridge), 4 MB flash, 28 broken-out GPIO pins, and an integrated LiPo charging circuit. Predates the Thing Plus (Feather-footprint) line.
