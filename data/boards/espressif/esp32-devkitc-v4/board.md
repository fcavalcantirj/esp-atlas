---
id: esp32-devkitc-v4
type: board
brand: espressif
name: ESP32-DevKitC V4
module: esp32-wroom-32e
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
power:
  battery_connector: false
  charging: false
io:
  gpio_free: 17
  gpio_pins:
  - 0
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
  - 9
  - 10
  - 11
  - 12
  - 13
  - 14
  - 15
  - 16
  - 17
  - 18
  - 19
  - 21
  - 22
  - 23
  - 25
  - 26
  - 27
  - 32
  - 33
  - 34
  - 35
  - 36
  - 39
notes:
- Single micro-USB (power/flash/comms via on-board USB-to-UART bridge); classic ESP32
  has no native USB
- Bridge chip model not named in the official user guide (omitted)
- Ships with several module variants; fixed here to esp32-wroom-32e
- Dimensions live only in a separate Dimensions PDF (omitted, not guessed)
- 'io.gpio_free=17 DERIVED, not quoted (SPEC-io-power.md §5.3). Header J2+J3 break
  out 32 pads total (quoted from the user guide pin tables: J2 = GPIO 9-14,25-27,32-36,39;
  J3 = GPIO 0-8,15-19,21-23). Subtracting esp32''s soc.reserved_pins that are exposed
  -- strapping {0,2,5,12,15} (5), input_only {34,35,36,39} (4), and usb_flash_tied
  {6,7,8,9,10,11} (6) -- gives 32 - 5 - 4 - 6 = 17. Math not vendor-stated; verify
  before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html
  verified: '2026-08-21'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html
  verified: '2026-08-26'
---

# ESP32-DevKitC V4

Espressif's small ESP32-WROOM/WROVER dev board: one micro-USB bridged to UART, most GPIOs on dual headers.
