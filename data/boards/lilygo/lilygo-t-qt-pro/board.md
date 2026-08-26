---
id: lilygo-t-qt-pro
type: board
brand: lilygo
name: T-QT Pro
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: t-qt
price_tier: cheap
power:
  charging: true
display: 0.85in 128x128 GC9107 IPS
notes:
- Base SKU ESP32-S3FN4R2 (4 MB flash, 2 MB PSRAM); ESP32-S3FN8 variant also offered (8 MB flash)
- Clock frequency 240MHz
- Battery charge and discharge circuit; battery voltage detection on IO04
- Wi-Fi 802.11 b/g/n, Bluetooth v5.0+BLE
- 'io OMITTED: product page "Onboard functions" spec lists only IO00+IO47
  (2 buttons) and IO04 (battery detection); the vendor TFT_eSPI pin setup
  (extras/Setup211_LilyGo_T_QT_Pro_S3.h) adds 6 more GPIOs consumed by the
  GC9107 display (TFT_RST=1, TFT_MOSI=2, TFT_SCLK=3, TFT_CS=5, TFT_DC=6,
  TFT_BL=10); this tiny circular-display board has no stated expansion header
  or free-pin count anywhere in the product page, README, or schematic, so
  gpio_exposed/gpio_free are left unset per cite-or-omit'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-qt-pro
  verified: '2026-08-22'
---

# T-QT Pro

Tiny ESP32-S3FN4R2 board with a 0.85in GC9107 IPS display and onboard battery charge/discharge circuitry.
