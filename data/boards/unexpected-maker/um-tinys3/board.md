---
id: um-tinys3
type: board
brand: unexpected-maker
name: Unexpected Maker TinyS3
soc: esp32-s3
flash_mb: 8
psram_mb: 8
form_factor: tinys3
price_tier: medium
dimensions_mm:
- 35
- 17.8
power:
  battery_connector: true
  charging: true
io:
  gpio_exposed: 17
notes:
- ESP32-S3FN8 chip; 8 MB internal flash, 8 MB external PSRAM
- LiPo battery via header + JST pads on bottom
- USB connector type not stated on the cited spec matrix (omitted)
- 'io.gpio_exposed=17 QUOTED: vendor page states "17 GPIO". io.gpio_free omitted:
  no official text pin table, only an image pinout reference card. io.power_out
  omitted: vendor states only "700mA 3.3V LDO Regulator" with no external-load
  framing (unlike FeatherS3/ProS3''s dedicated LDO2)'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/tinys3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/tinys3.html
  verified: '2026-08-26'
---

# Unexpected Maker TinyS3

Tiny ESP32-S3 board (ESP32-S3FN8) in a 35 x 17.8 mm outline: 8 MB internal flash, 8 MB external PSRAM, and LiPo header + JST-pad charging.
