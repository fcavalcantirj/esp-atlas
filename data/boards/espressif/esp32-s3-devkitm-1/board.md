---
id: esp32-s3-devkitm-1
type: board
brand: espressif
name: ESP32-S3-DevKitM-1
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
extras:
- rgb-led
notes:
- 'Micro-USB UART-bridge port; the ESP32-S3''s native full-speed USB OTG interface
  is also present'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-S3-MINI-1 or -1U module built on the ESP32-S3FN8 chip, 8 MB flash
  integrated in the chip package; no PSRAM
- Addressable RGB LED on GPIO48
- Dimensions only in separate PDF/DXF files (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitm-1/user_guide.html
  verified: '2026-08-22'
---

# ESP32-S3-DevKitM-1

Compact ESP32-S3-MINI-1 board with a micro-USB UART bridge and a GPIO48 addressable RGB LED.
