---
id: esp32-h2-devkitm-1
type: board
brand: espressif
name: ESP32-H2-DevKitM-1
soc: esp32-h2
form_factor: devkit
price_tier: cheap
usb:
  connector: usb-c
extras:
- rgb-led
notes:
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-H2 USB port (USB
  2.0 full speed, up to 12 Mbps)'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-H2-MINI-1 or -1U module, 4 MB flash integrated in the chip package;
  no PSRAM
- Addressable RGB LED on GPIO8
- Dimensions only in a separate Dimensions PDF (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-08-22'
---

# ESP32-H2-DevKitM-1

Compact ESP32-H2-MINI-1 board with dual USB-C (UART bridge + native USB) and a GPIO8 addressable RGB LED.
