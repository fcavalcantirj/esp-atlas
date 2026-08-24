---
id: esp32-c6-devkitm-1
type: board
brand: espressif
name: ESP32-C6-DevKitM-1
soc: esp32-c6
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: usb-c
extras:
- rgb-led
notes:
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-C6 USB port'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-C6-MINI-1 or -1U module built on the ESP32-C6FH4 chip, 4 MB flash
  integrated in the chip package; no PSRAM
- Addressable RGB LED on GPIO8
- Wi-Fi 6 / BLE 5 / Zigbee 3.0 / Thread 1.3 (802.15.4)
- Dimensions only in a separate Dimensions PDF (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitm-1/user_guide.html
  verified: '2026-08-22'
---

# ESP32-C6-DevKitM-1

Compact ESP32-C6-MINI-1 board with dual USB-C (UART bridge + native USB) and a GPIO8 addressable RGB LED.
