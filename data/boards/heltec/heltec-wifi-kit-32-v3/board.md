---
id: heltec-wifi-kit-32-v3
type: board
brand: heltec
name: WiFi Kit 32 (V3)
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: heltec
price_tier: medium
dimensions_mm:
- 50.2
- 25.5
- 10.2
usb:
  connector: usb-c
  bridge: cp2102
power:
  battery_connector: true
  charging: true
display: 0.96in 128x64 OLED
io:
  gpio_exposed: 28
  gpio_free: 18
notes:
- ESP32-S3FN8, 8 MB SiP flash, no external PSRAM
- WiFi + Bluetooth 5 only; no LoRa radio (the LoRa variant is the WiFi LoRa 32 V3)
- 'io.gpio_exposed=28 QUOTED: Heltec''s WiFi Kit 32 datasheet Pin Definition table
  lists Header J2 GPIO {44,43,36,35,34,33,47,48,26,21,20,19,0} (13 pins) and Header
  J3 GPIO {37,46,45,42,41,40,39,38,1,2,3,4,5,6,7} (15 pins) -- 28 header-exposed
  pads total; the OLED''s I2C data lines (SDA_OLED/SCL_OLED, GPIO17/18) are wired
  directly to the display and are not routed to either header'
- 'io.gpio_free=18 DERIVED: subtracting esp32-s3''s soc.reserved_pins that are
  exposed here (strapping {0,3,45,46}: all 4 present; usb_flash_tied {19,20,35,36,37}:
  all 5 present -- 9 total) and the OLED reset line shared with the header (GPIO21,
  labeled "OLED RST" in the same datasheet table) gives 28 - 9 - 1 = 18'
sources:
- field: '*'
  url: https://heltec.org/project/wifi-kit32-v3/
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/WiFi_Kit_32/WiFi%20Kit32.pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://resource.heltec.cn/download/WiFi_Kit_32/WiFi%20Kit32.pdf
  verified: '2026-08-26'
---

# WiFi Kit 32 (V3)

ESP32-S3FN8 WiFi/BT dev board with a 0.96in OLED, native USB-C, and lithium battery charging — the non-LoRa sibling of the WiFi LoRa 32 V3.
