---
id: heltec-wireless-tracker
type: board
brand: heltec
name: Wireless Tracker
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: heltec
price_tier: medium
dimensions_mm:
- 65.48
- 28.06
- 13.52
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 0.96in 160x80 TFT LCD
extras:
- lora
- gps
notes:
- ESP32-S3FN8
- SX1262 LoRa transceiver; UC6580 L1+L2/L5 dual-frequency GNSS module
- Separate IPEX (U.FL) antenna interfaces for LoRa and GNSS
- ESP32-S3FN8 ordering code is 8 MB in-package flash with no PSRAM, per Espressif's ESP32-S3 series datasheet
sources:
- field: '*'
  url: https://heltec.org/project/wireless-tracker/
  verified: '2026-08-22'
- field: flash_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-08-24'
- field: psram_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-08-24'
---

# Wireless Tracker

ESP32-S3FN8 + SX1262 LoRa dev board with an onboard UC6580 dual-frequency GNSS module, 0.96in TFT LCD, USB-C, and lithium battery charging.
