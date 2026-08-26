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
  reflect this external-use LDO2, not the shared LDO1. io.gpio_free omitted: no
  official text pin table, only an image pinout reference card'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/feathers3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/feathers3.html
  verified: '2026-08-26'
- field: io.power_out
  url: https://esp32s3.com/feathers3.html
  verified: '2026-08-26'
---

# Unexpected Maker FeatherS3

ESP32-S3 board in the Adafruit Feather footprint: 16 MB flash, 8 MB PSRAM, LiPo header + JST PH charging, and two STEMMA QT / Qwiic ports.
