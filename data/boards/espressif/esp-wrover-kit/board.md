---
id: esp-wrover-kit
type: board
brand: espressif
name: ESP-WROVER-KIT
soc: esp32
form_factor: devkit
price_tier: medium
usb:
  connector: micro-usb
  bridge: ft2232hl
extras:
- rgb-led
notes:
- USB 2.0 A-to-Micro-B cable; FT2232HL provides both the UART bridge and on-board
  JTAG debugging
- Carries an ESP32-WROVER-E module with 64-Mbit (8 MB) PSRAM
- Four diagnostic red LEDs on FT2232HL GPIOs, plus a red 5V Power-On LED and an
  RGB LED (GPIO0/GPIO2/GPIO4)
- Dimensions not provided in the user guide (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
  verified: '2026-08-22'
---

# ESP-WROVER-KIT

ESP32-WROVER-E development/debug board with a built-in FT2232HL JTAG debugger and an onboard RGB LED.
