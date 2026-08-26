---
id: lilygo-t-display-s3-amoled
type: board
brand: lilygo
name: T-Display S3 AMOLED
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: t-display-amoled
price_tier: medium
power:
  battery_connector: true
display: 1.91in 240x536 RM67162 AMOLED QSPI
notes:
- ESP32-S3R8 dual-core LX7; 16 MB flash, 8 MB PSRAM
- Display active area 19.8x44.22mm, full IPS-equivalent viewing angle; touch and non-touch variants
- Battery voltage detection on IO04
- Wi-Fi 2.4GHz + Bluetooth 5 (LE)
- 'io OMITTED: the official GitHub repo''s pin-definition header
  (examples/factory/pins_config.h) only names pins consumed by the onboard
  AMOLED QSPI display, LED, battery-ADC, and 2 buttons (GPIO 0,4,5,6,7,17,18,
  21,38,47,48); no expansion-header pin list or exposed-pad count is given in
  text anywhere in the repo or product page -- the only pinout artifact is an
  un-OCR''d image, so gpio_exposed/gpio_free are left unset per cite-or-omit'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-display-s3-amoled
  verified: '2026-08-22'
---

# T-Display S3 AMOLED

ESP32-S3R8 board with a 1.91in RM67162 AMOLED display over QSPI, offered in touch and non-touch variants.
