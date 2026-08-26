---
id: m5cardputer
type: board
brand: m5stack
name: Cardputer
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-cardputer
price_tier: medium
dimensions_mm:
- 84.0
- 54.0
- 19.7
usb:
  bridge: native
power:
  battery_connector: true
  charging: true
display: 1.14in 240x135 ST7789V2
extras:
- sd-card
- mic
- speaker
io:
  gpio_exposed: 2
  gpio_free: 2
notes:
- ESP32-S3FN8; 8 MB flash, no PSRAM
- 56-key QWERTY keyboard (4x14), SPM1423 MEMS mic, NS4168 8ohm/1W I2S speaker, IR
  emitter, microSD slot, 120mAh internal battery plus 1400mAh base battery; physical
  USB connector type not specified on the official page (omitted) — page lists "USB
  OTG, USB Serial/JTAG" (native ESP32-S3 USB, no separate bridge chip)
- 'io.gpio_exposed=2 COUNTED: the only user-accessible header is "1 x HY2.0-4P
  port for connecting and expanding I2C sensors", pinout "Yellow: G2, White: G1"
  = {1,2}. Every other pin on the page (mic G46/G43, microSD G12/G14/G40/G39,
  display G38/G33/G34/G35/G36/G37, keyboard matrix G3-G15, speaker/IR G41/G42/G43/G44,
  boot button G0) is hard-wired to an onboard peripheral, not header-exposed.
  io.gpio_free=2 DERIVED: subtracting esp32-s3''s soc.reserved_pins (strapping
  {0,3,45,46}, usb_flash_tied {19,20,35,36,37}) -- neither G1 nor G2 falls in
  either set -- gives 2 - 0 = 2. No max Grove/rail output current stated on this
  page, so power_out is omitted.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-26'
---

# Cardputer

84x54mm ESP32-S3 pocket computer: QWERTY keyboard, 1.14in display, mic, speaker, IR emitter, microSD, dual built-in batteries.
