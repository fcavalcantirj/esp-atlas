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
io:
  gpio_exposed: 28
  gpio_free: 11
notes:
- ESP32-S3FN8
- SX1262 LoRa transceiver; UC6580 L1+L2/L5 dual-frequency GNSS module
- Separate IPEX (U.FL) antenna interfaces for LoRa and GNSS
- ESP32-S3FN8 ordering code is 8 MB in-package flash with no PSRAM, per Espressif's ESP32-S3 series datasheet
- 'io.gpio_exposed=28 QUOTED: Heltec''s Wireless Tracker datasheet Pin Definition
  table lists Header J2 GPIO {44,43,36,35,34,33,47,48,26,21,20,19,0} (13 pins)
  and Header J3 GPIO {37,46,45,42,41,40,39,38,1,2,3,4,5,6,7} (15 pins) -- 28
  header-exposed pads total, the same carrier layout as the sibling V3 boards;
  the SX1262''s SPI bus (GPIO8-11) and RST/DIO1/BUSY (GPIO12-14) are wired
  off-header directly to the radio'
- 'io.gpio_free=11 DERIVED: subtracting esp32-s3''s soc.reserved_pins that are
  exposed here (strapping {0,3,45,46}: all 4 present; usb_flash_tied {19,20,35,36,37}:
  all 5 present -- 9 total), then the onboard ST7735S TFT and UC6580 GNSS pins
  per meshtastic''s heltec_wireless_tracker variant.h -- TFT (CS=38, DC=40,
  MOSI=42, SCK=41, RESET=39, backlight=21: 6 new pins) and GNSS (RX=33, TX=34,
  RESET=35, PPS=36; RESET/PPS are already removed via reserved_pins, so 2 new:
  33,34) -- gives 28 - 9 - 6 - 2 = 11'
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
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/Wireless_Tracker/Wireless%20tracke.pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/meshtastic/firmware/blob/master/variants/esp32s3/heltec_wireless_tracker/variant.h
  verified: '2026-08-26'
---

# Wireless Tracker

ESP32-S3FN8 + SX1262 LoRa dev board with an onboard UC6580 dual-frequency GNSS module, 0.96in TFT LCD, USB-C, and lithium battery charging.
