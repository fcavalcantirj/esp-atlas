---
id: lilygo-t-display-s3
type: board
brand: lilygo
name: T-Display-S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: devkit
price_tier: medium
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 1.9in 170x320 IPS ST7789V
io:
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 100
notes:
- 16 MB flash, 8 MB PSRAM (ESP32-S3R8)
- JST-GH battery connector; STEMMA QT/Qwiic; Touch and non-Touch variants
- 'io.power_out QUOTED: vendor README Electrical Parameters section states "3V pin
  header load does not exceed 100mA" (recorded as the board''s 3.3V logic rail);
  the 5V pin header is USB-C passthrough with no fixed rating ("load capacity depends
  on the USB-C adapter"), so only the 3V/100mA figure is recorded'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-display-s3
  verified: '2026-08-21'
- field: '*'
  url: https://github.com/Xinyuan-LilyGO/T-Display-S3
  verified: '2026-08-21'
- field: io.power_out
  url: https://github.com/Xinyuan-LilyGO/T-Display-S3
  verified: '2026-08-26'
---

# T-Display-S3

ESP32-S3R8 dev board with a 1.9in 170x320 ST7789V IPS display, native USB-C, and JST battery charging.
