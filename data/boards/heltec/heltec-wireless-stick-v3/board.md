---
id: heltec-wireless-stick-v3
type: board
brand: heltec
name: Wireless Stick (V3)
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: heltec
price_tier: medium
dimensions_mm:
- 58.08
- 22.6
- 8.2
usb:
  connector: usb-c
  bridge: cp2102
power:
  battery_connector: true
  charging: true
display: 0.49in 64x32 OLED
extras:
- lora
io:
  gpio_exposed: 28
  gpio_free: 18
notes:
- ESP32-S3FN8, 8 MB SiP flash, no external PSRAM
- SX1262 LoRa transceiver
- 'io.gpio_exposed=28 QUOTED: Heltec''s Wireless Stick (V3) datasheet Pin Definition
  table lists Header J2 GPIO {21,44,43,33,34,35,36,37,38,39,40,41,42,45,46} (15
  pins) and Header J3 GPIO {19,20,0,47,48,26,7,6,5,4,3,2,1} (13 pins) -- 28
  header-exposed pads total (same carrier design as the sibling V3 boards, just
  split differently across the two headers); the SX1262''s SPI bus (GPIO8-11)
  and RST/BUSY/DIO0 (GPIO12-14), plus the OLED''s I2C data lines (SDA_OLED/SCL_OLED,
  GPIO17/18), are wired directly to the onboard radio/display and never reach
  either header'
- 'io.gpio_free=18 DERIVED: subtracting esp32-s3''s soc.reserved_pins that are
  exposed here (strapping {0,3,45,46}: all 4 present; usb_flash_tied {19,20,35,36,37}:
  all 5 present -- 9 total) and the OLED reset line shared with the header (GPIO21,
  labeled "OLED RST" in the datasheet) gives 28 - 9 - 1 = 18'
sources:
- field: '*'
  url: https://heltec.org/project/wireless-stick-v3/
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/Wireless_Stick_V3/HTIT-WS_V3(Rev1.0).pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://resource.heltec.cn/download/Wireless_Stick_V3/HTIT-WS_V3(Rev1.0).pdf
  verified: '2026-08-26'
---

# Wireless Stick (V3)

ESP32-S3FN8 + SX1262 LoRa dev board in a slim stick form factor with a tiny 0.49in OLED, native USB-C, and lithium battery charging.
