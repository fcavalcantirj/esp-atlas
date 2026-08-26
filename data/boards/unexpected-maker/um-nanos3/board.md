---
id: um-nanos3
type: board
brand: unexpected-maker
name: Unexpected Maker NanoS3
soc: esp32-s3
flash_mb: 8
psram_mb: 8
form_factor: nanos3
price_tier: medium
dimensions_mm:
- 28
- 11
io:
  gpio_exposed: 27
notes:
- ESP32-S3FN8 chip; 8 MB internal flash, 8 MB external PSRAM
- Very small 28 x 11 mm outline
- USB connector type not stated on the cited spec matrix (omitted)
- 'io.gpio_exposed=27 QUOTED: vendor page states "27 GPIO". io.gpio_free omitted:
  no official text pin table, only an image pinout reference card. io.power_out
  omitted: vendor states only "700mA 3.3V LDO Regulator" with no external-load
  framing (unlike FeatherS3/ProS3''s dedicated LDO2)'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/nanos3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/nanos3.html
  verified: '2026-08-26'
---

# Unexpected Maker NanoS3

Ultra-compact ESP32-S3 board (ESP32-S3FN8) at just 28 x 11 mm: 8 MB internal flash and 8 MB external PSRAM.
