---
id: m5stack-cores3
type: board
brand: m5stack
name: CoreS3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: m5-core
price_tier: medium
dimensions_mm:
- 54.0
- 54.0
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 2.0in 320x240 IPS ILI9342C capacitive touch
extras:
- sd-card
- imu
- mic
- camera
- speaker
- magnetometer
- rtc
- touch
io:
  gpio_free: 6
notes:
- 16 MB flash, 8 MB PSRAM
- GC0308 camera, dual mic (ES7210), 1W speaker (AW88298), BMI270 IMU, BMM150 mag,
  BM8563 RTC, AXP2101 PMIC, 500mAh battery
- 'io.gpio_free=6 DERIVED, not quoted (SPEC-io-power.md §5.3). Vendor pinmap page
  states the three HY2.0-4P ports: "PORT.A | G2 | G1", "PORT.B | G9 | G8", "PORT.C
  | G17 | G18" -- 6 pads total (1, 2, 8, 9, 17, 18), none shared with the
  camera/LCD/SD/touch/mic/RTC/IMU pins the same page lists elsewhere. Subtracting
  esp32-s3''s soc.reserved_pins that are exposed on those 6 -- none of strapping
  {0,3,45,46} or usb_flash_tied {19,20,35,36,37} match -- leaves all 6 free: 6 -
  0 = 6. The 40-pin M-Bus header is excluded from this count: it re-exposes the
  same SoC pins already wired to onboard camera/LCD/SD/touch/mic, so those pads
  are not free for independent use. Math not vendor-stated; verify before
  treating as exact.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/CoreS3
  verified: '2026-08-21'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/CoreS3
  verified: '2026-08-26'
---

# CoreS3

54x54mm ESP32-S3 core unit: 2.0in capacitive-touch IPS display, camera, dual mics, speaker, IMU, microSD, USB-C.
