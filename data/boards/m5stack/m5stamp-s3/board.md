---
id: m5stamp-s3
type: board
brand: m5stack
name: Stamp-S3
aka:
- m5stack_stamp_s3
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-stamp
price_tier: cheap
dimensions_mm:
- 24.0
- 18.0
- 4.7
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_exposed: 23
  gpio_free: 20
notes:
- ESP32-S3FN8; 8 MB flash. ESP32-S3FN8 ordering code has no PSRAM, per Espressif's
  ESP32-S3 series datasheet
- WS2812B-2020 programmable RGB LED, 23 GPIO exposed, no onboard battery
- 'io.gpio_exposed=23 QUOTED: vendor page states "IO Ports × 23", pins G0/G1/G2/G3/G4/G5/G6/G7/G8/G9/G10/G11/G12/G13/G14/G15/G39/G40/G41/G42/G43/G44/G46'
- 'io.gpio_free=20 DERIVED, not quoted (SPEC-io-power.md §5.3). Exposed pads {G0-G15,G39,G40,G41,G42,G43,G44,G46}
  (23, quoted from vendor IO Ports list). Subtracting esp32-s3''s soc.reserved_pins
  that are exposed -- strapping {0,3,45,46}: {0,3,46} exposed (3), usb_flash_tied
  {19,20,35,36,37}: none exposed (0) -- gives 23 - 3 - 0 = 20.'
getting_started: https://docs.m5stack.com/en/core/StampS3
images:
  photo: https://static-cdn.m5stack.com/resource/docs/products/core/StampS3/img-964c4df6-26ff-49e0-9950-87ee1a0f3b18.webp
  pinout: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/684/S007_PinMap_01.jpg
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/stamps3
  verified: '2026-08-22'
- field: psram_mb
  url: https://docs.m5stack.com/en/core/StampS3
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/stamps3
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/stamps3
  verified: '2026-08-26'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/m5stack-stamps3.json
  verified: '2026-09-07'
- field: getting_started
  url: https://docs.m5stack.com/en/core/StampS3
  verified: '2026-09-11'
- field: images
  url: https://docs.m5stack.com/en/core/StampS3
  verified: '2026-09-11'
---

# Stamp-S3

24x18mm ESP32-S3 stamp module: USB-C, programmable RGB LED, 23 exposed GPIO.
