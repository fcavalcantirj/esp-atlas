---
id: um-pros3
type: board
brand: unexpected-maker
name: Unexpected Maker ProS3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: pros3
price_tier: medium
dimensions_mm:
- 53
- 17.8
power:
  battery_connector: true
  charging: true
extras:
- stemma-qt
io:
  gpio_exposed: 27
  gpio_free: 22
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 700
notes:
- 16 MB external flash, 8 MB external PSRAM
- LiPo battery via header + Microblade connector on top
- One STEMMA QT / Qwiic port
- USB connector type not stated on the cited spec matrix (omitted)
- 'io.gpio_exposed=27 QUOTED: vendor page states "27x GPIO including castellated
  headers"'
- 'io.power_out QUOTED: vendor page states "2x 700mA 3.3V LDO Regulators"; LDO2
  is described as "for you to use to connect external 3V3 modules, sensors and
  peripherals" (EN tied to IO17, auto-shuts down in deep sleep) -- rail_v/rail_ma_max
  reflect this external-use LDO2, not the shared LDO1'
- 'io.gpio_free=22 DERIVED: CircuitPython''s board pin table (unexpectedmaker_pros3/pins.c)
  lists 28 IO-numbered pins {0-9,12-16,17,21,34-42,43,44}; excluding GPIO17 (LDO2/NeoPixel-power
  enable -- onboard-dedicated despite carrying an IO17 alias; NeoPixel data GPIO18
  carries no IO-alias) leaves 27 GPIO {0-9,12,13,14,15,16,21,34,35,36,37,38,39,40,41,42,43,44},
  matching vendor''s "27" exactly. Subtracting esp32-s3''s soc.reserved_pins present
  in that 27-pin set (strapping {0,3}: 2; usb_flash_tied {35,36,37}: 3 -- 5 total)
  gives 27 - 5 = 22'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/pros3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/pros3.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/unexpectedmaker_pros3/pins.c
  verified: '2026-08-26'
- field: io.power_out
  url: https://esp32s3.com/pros3.html
  verified: '2026-08-26'
---

# Unexpected Maker ProS3

Feature-loaded ESP32-S3 board: 16 MB flash, 8 MB PSRAM, LiPo header + Microblade charging, and a STEMMA QT / Qwiic port, in a compact 53 x 17.8 mm outline.
