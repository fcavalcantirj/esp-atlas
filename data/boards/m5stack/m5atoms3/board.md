---
id: m5atoms3
type: board
brand: m5stack
name: AtomS3
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
- 'io.gpio_exposed=8 COUNTED (page has no single "IO x N" summary line): bottom
  header states "The bottom reserves 6 GPIO and power pins" listing G5/G6/G7/G8/G38/G39,
  plus the separate HY2.0-4P expansion port pinout "Yellow: G2, White: G1" -- pad
  set {1,2,5,6,7,8,38,39} = 8. io.gpio_free=8 DERIVED: subtracting esp32-s3''s
  soc.reserved_pins (strapping {0,3,45,46}, usb_flash_tied {19,20,35,36,37}) --
  none of the 8 exposed pads fall in either set -- gives 8 - 0 = 8. G38/G39 also
  carry the onboard MPU6886 I2C bus (shared, multi-drop) but are not subtracted
  since I2C sharing doesn''t consume the pad exclusively; no display/PSRAM pins
  overlap the exposed set (display uses G21/G17/G15/G33/G34/G16, psram_mb=0).
  No max Grove/rail output current stated on this page, so power_out is omitted.'
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
---

# AtomS3

24x24mm ESP32-S3 atom unit: 0.85in IPS display, IMU, IR transmitter, USB-C.
