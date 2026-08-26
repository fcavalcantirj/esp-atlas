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
io:
  gpio_free: 30
notes:
- 'Micro-USB UART-bridge port; the ESP32-S3''s native full-speed USB OTG interface
  is also present'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-S3-MINI-1 or -1U module built on the ESP32-S3FN8 chip, 8 MB flash
  integrated in the chip package; no PSRAM
- Addressable RGB LED on GPIO48
- Dimensions only in separate PDF/DXF files (omitted)
- 'io.gpio_free=30 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J1+J3 break
  out 39 pads total (quoted from the user guide pin tables: J1 = GPIO 0-18; J3 =
  GPIO 19-21,26,33-48). Subtracting esp32-s3''s soc.reserved_pins that are exposed
  -- strapping {0,3,45,46} (4) and usb_flash_tied {19,20,35,36,37} (5) -- gives
  39 - 4 - 5 = 30. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitm-1/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitm-1/user_guide.html
  verified: '2026-08-26'
---

# ESP32-S3-DevKitM-1

Compact ESP32-S3-MINI-1 board with a micro-USB UART bridge and a GPIO48 addressable RGB LED.
