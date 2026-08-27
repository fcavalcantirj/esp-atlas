---
id: esp32-c3-devkitm-1
type: board
brand: espressif
name: ESP32-C3-DevKitM-1
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
extras:
- rgb-led
io:
  gpio_free: 10
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
  - 18
  - 19
  - 20
  - 21
notes:
- Single micro-USB (power/flash/comms via on-board USB-to-UART bridge)
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-C3-MINI-1 or -1U SiP module, 4 MB flash, no PSRAM
- Addressable RGB LED on GPIO8
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=10 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J1+J3 break
  out 15 pads total (quoted from the user guide pin tables: J1 = GPIO 0-3,10; J3
  = GPIO 4-9,18-21). Subtracting esp32-c3''s soc.reserved_pins that are exposed
  -- strapping {2,8,9} (3) and usb_flash_tied {18,19} (2) -- gives 15 - 3 - 2 = 10.
  Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
  verified: '2026-08-26'
---

# ESP32-C3-DevKitM-1

Compact ESP32-C3-MINI-1 board with a single micro-USB (UART bridge) port and a GPIO8 addressable RGB LED.
