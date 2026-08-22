---
id: esp32-devkitc-v4
type: board
brand: espressif
name: ESP32-DevKitC V4
module: esp32-wroom-32e
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
power:
  battery_connector: false
  charging: false
notes:
- Single micro-USB (power/flash/comms via on-board USB-to-UART bridge); classic ESP32
  has no native USB
- Bridge chip model not named in the official user guide (omitted)
- Ships with several module variants; fixed here to esp32-wroom-32e
- Dimensions live only in a separate Dimensions PDF (omitted, not guessed)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html
  verified: '2026-08-21'
---

# ESP32-DevKitC V4

Espressif's small ESP32-WROOM/WROVER dev board: one micro-USB bridged to UART, most GPIOs on dual headers.
