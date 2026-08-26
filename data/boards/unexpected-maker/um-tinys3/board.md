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
  gpio_free: 12
notes:
- ESP32-S3FN8 chip; 8 MB internal flash, 8 MB external PSRAM
- LiPo battery via header + JST pads on bottom
- USB connector type not stated on the cited spec matrix (omitted)
- 'io.gpio_exposed=17 QUOTED: vendor page states "17 GPIO". io.power_out omitted:
  vendor states only "700mA 3.3V LDO Regulator" with no external-load framing
  (unlike FeatherS3/ProS3''s dedicated LDO2)'
- 'io.gpio_free=12 DERIVED: CircuitPython''s board pin table (unexpectedmaker_tinys3/pins.c)
  lists exactly 17 IO-numbered pins, GPIO {0-9, 21, 34,35,36,37, 43,44} -- matches
  vendor''s "17" exactly (NeoPixel/NeoPixel-power on GPIO18/17 and VBAT/VBUS sense
  on GPIO10/33 all carry no IO-alias and are excluded). Subtracting esp32-s3''s
  soc.reserved_pins present in that 17-pin set (strapping {0,3}: 2; usb_flash_tied
  {35,36,37}: 3 -- 5 total) gives 17 - 5 = 12'
sources:
- field: '*'
  url: https://unexpectedmaker.com/shop/tinys3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://esp32s3.com/tinys3.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/unexpectedmaker_tinys3/pins.c
  verified: '2026-08-26'
---

# Unexpected Maker TinyS3

Tiny ESP32-S3 board (ESP32-S3FN8) in a 35 x 17.8 mm outline: 8 MB internal flash, 8 MB external PSRAM, and LiPo header + JST-pad charging.
