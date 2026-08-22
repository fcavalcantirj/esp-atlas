---
id: esp32-c3-devkitm-1
type: board
brand: espressif
name: ESP32-C3-DevKitM-1
soc: esp32-c3
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
extras:
- rgb-led
notes:
- Single micro-USB (power/flash/comms via on-board USB-to-UART bridge)
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-C3-MINI-1 or -1U SiP module, 4 MB flash, no PSRAM
- Addressable RGB LED on GPIO8
- Dimensions only in a separate Dimensions PDF (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
  verified: '2026-08-22'
---

# ESP32-C3-DevKitM-1

Compact ESP32-C3-MINI-1 board with a single micro-USB (UART bridge) port and a GPIO8 addressable RGB LED.
