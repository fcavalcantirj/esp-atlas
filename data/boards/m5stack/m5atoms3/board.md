---
id: m5atoms3
type: board
brand: m5stack
name: AtomS3
aka:
- m5stack_atoms3
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-atom
price_tier: cheap
dimensions_mm:
- 24.0
- 24.0
- 12.9
usb:
  connector: usb-c
display: 0.85in 128x128 IPS SPI
extras:
- imu
io:
  gpio_exposed: 8
  gpio_free: 8
notes:
- ESP32-S3FN8; 8 MB flash, no PSRAM
- MPU6886 6-axis IMU (I2C 0x68), programmable button below screen, IR transmitter,
  HY2.0-4P expansion port, no onboard battery
- 'io.gpio_exposed=8 COUNTED (page has no single "IO x N" summary line): bottom header
  states "The bottom reserves 6 GPIO and power pins" listing G5/G6/G7/G8/G38/G39,
  plus the separate HY2.0-4P expansion port pinout "Yellow: G2, White: G1" -- pad
  set {1,2,5,6,7,8,38,39} = 8. io.gpio_free=8 DERIVED: subtracting esp32-s3''s soc.reserved_pins
  (strapping {0,3,45,46}, usb_flash_tied {19,20,35,36,37}) -- none of the 8 exposed
  pads fall in either set -- gives 8 - 0 = 8. G38/G39 also carry the onboard MPU6886
  I2C bus (shared, multi-drop) but are not subtracted since I2C sharing doesn''t consume
  the pad exclusively; no display/PSRAM pins overlap the exposed set (display uses
  G21/G17/G15/G33/G34/G16, psram_mb=0). No max Grove/rail output current stated on
  this page, so power_out is omitted.'
getting_started: https://docs.m5stack.com/en/core/AtomS3
images:
  photo: https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/core/AtomS3/4.webp
  pinout: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/472/C123_PinMap_01.jpg
platformio_definitions:
- id: m5stack-atoms3
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: f506d34839aead33f9bf75be5c9f49a1c0b98d6d0bc8ed75bd853e4b6e0bb233
- id: m5stack-atoms3
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: df41eb1418353a1b99ecc39afd94c14535a947b2a755798b0701606651535664
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/AtomS3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/AtomS3
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/AtomS3
  verified: '2026-08-26'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/m5stack-atoms3.json
  verified: '2026-09-07'
- field: getting_started
  url: https://docs.m5stack.com/en/core/AtomS3
  verified: '2026-09-11'
- field: images
  url: https://docs.m5stack.com/en/core/AtomS3
  verified: '2026-09-11'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/m5stack-atoms3.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/m5stack-atoms3.json
  verified: '2026-11-22'
---

# AtomS3

24x24mm ESP32-S3 atom unit: 0.85in IPS display, IMU, IR transmitter, USB-C.
