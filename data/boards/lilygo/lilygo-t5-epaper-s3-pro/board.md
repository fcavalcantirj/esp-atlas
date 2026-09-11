---
id: lilygo-t5-epaper-s3-pro
type: board
brand: lilygo
name: T5 E-Paper S3 Pro
aka:
- lilygo_t5_epd_s3_pro
- T5S3-4.7-e-paper-PRO
module: esp32-s3-wroom-1
flash_mb: 16
psram_mb: 8
display: 4.7in 960x540 e-ink ED047TC1 (16 gray, GT911 capacitive touch)
power:
  battery_connector: true
  charging: true
notes:
- 'Vendor repo README: "ESP32-S3-WROOM-1" with "16M / 8M" flash and PSRAM; display
  "ED047TC1 (4.7 inches, 960x540 , 16 gray)"; touch "GT911 (0x5D)"; battery "3.7V-1500mAh"
  with "BQ25896 (0x6B), BQ27220 (0x55)" charger and fuel gauge; TPS65185 e-ink PMIC;
  PCF8563 RTC; PCA9535PW GPIO expander'
- 'Three variants share the board: "T5 E-Paper S3 Pro" (GPS + LoRa SX1262 + TPS65185),
  "Pro Lite" (GPS and LoRa omitted, same schematic), "H752" (LoRa included, GPS and
  TPS65185 absent)'
- USB connector type and any USB-UART bridge are not stated in the README (omitted)
- aka "lilygo_t5_epd_s3_pro" is the device token draftling uses for its release binaries
getting_started: https://lilygo.cc/products/t5-e-paper-s3-pro
images:
  photo: https://lilygo.cc/cdn/shop/files/T5-4_7.jpg
sources:
- field: '*'
  url: https://github.com/Xinyuan-LilyGO/T5S3-4.7-e-paper-PRO
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
- field: getting_started
  url: https://lilygo.cc/products/t5-e-paper-s3-pro
  verified: '2026-09-11'
- field: images
  url: https://lilygo.cc/products/t5-e-paper-s3-pro
  verified: '2026-09-11'
---

# LILYGO T5 E-Paper S3 Pro

A 4.7-inch 960x540 e-paper board on an ESP32-S3-WROOM-1 (16 MB flash, 8 MB PSRAM) with capacitive touch, a 1500 mAh battery and, on the Pro variant, GPS and LoRa.
