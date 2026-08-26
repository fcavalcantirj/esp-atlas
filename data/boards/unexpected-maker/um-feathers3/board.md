---
id: um-feathers3
type: board
brand: unexpected-maker
name: Unexpected Maker FeatherS3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: feather
price_tier: medium
dimensions_mm:
- 52.3
- 22.9
power:
  battery_connector: true
  charging: true
extras:
- stemma-qt
io:
  gpio_exposed: 21
  gpio_free: 16
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 700
notes:
- 16 MB external flash, 8 MB external PSRAM
- Adafruit Feather footprint
- LiPo battery via header + JST PH connector on top
- Two STEMMA QT / Qwiic ports (one on each LDO)
- USB connector type not stated on the cited spec matrix (omitted)
- 'io.gpio_exposed=21 QUOTED: vendor page states "21x GPIO including castellated
  headers"'
- 'io.power_out QUOTED: vendor page states "2x 700mA 3.3V LDO Regulators"; LDO2
  is described as "for you to use to connect external 3V3 modules, sensors and
  peripherals" (EN tied to IO39, auto-shuts down in deep sleep) -- rail_v/rail_ma_max
  reflect this external-use LDO2, not the shared LDO1'
- 'io.gpio_free=16 DERIVED: CircuitPython''s board pin table (unexpectedmaker_feathers3/pins.c)
  maps the 21 header-labeled D-pins (D0,D1,D4,D5,D6,D9-D19,D21-D25) to GPIO {44,43,0,33,38,1,3,7,10,11,17,18,14,12,6,5,8,9,37,35,36}
  -- the count matches vendor''s "21" exactly and excludes onboard-dedicated pins
  (GPIO2 VBAT sense, GPIO34 VBUS sense, GPIO39 LDO2/NeoPixel enable, GPIO40 NeoPixel
  data, GPIO41 antenna switch, GPIO4 ambient-light sensor, GPIO15/16 second STEMMA
  QT I2C) that carry no D-number. Subtracting esp32-s3''s soc.reserved_pins present
  in that 21-pin set (strapping {0,3}: 2: usb_flash_tied {35,36,37}: 3 -- 5 total)
  gives 21 - 5 = 16'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/feathers3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/feathers3.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/unexpectedmaker_feathers3/pins.c
  verified: '2026-08-26'
- field: io.power_out
  url: https://esp32s3.com/feathers3.html
  verified: '2026-08-26'
---

# Unexpected Maker FeatherS3

ESP32-S3 board in the Adafruit Feather footprint: 16 MB flash, 8 MB PSRAM, LiPo header + JST PH charging, and two STEMMA QT / Qwiic ports.
