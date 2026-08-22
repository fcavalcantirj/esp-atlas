---
id: esp32-s2-saola-1
type: board
brand: espressif
name: ESP32-S2-Saola-1
soc: esp32-s2
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
extras:
- rgb-led
notes:
- Single micro-USB port for power, flashing and UART communication
- Bridge chip model not named in the official user guide (omitted)
- EOL/legacy board; guide's worked example uses ESP32-S2-WROVER, 4 MB flash, 2 MB
  PSRAM, but board also supports WROVER-I/WROOM/WROOM-I module variants (fixed
  spec omitted since it varies by module fitted)
- Addressable RGB LED (WS2812) on GPIO18
- Dimensions only in a separate Dimensions PDF (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html
  verified: '2026-08-22'
---

# ESP32-S2-Saola-1

Small ESP32-S2 board (EOL) with a single micro-USB port and a GPIO18 addressable RGB LED; most I/O broken out to dual headers.
