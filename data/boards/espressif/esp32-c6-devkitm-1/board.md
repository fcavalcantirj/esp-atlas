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
  - 12
  - 13
  - 14
  - 15
  - 16
  - 17
  - 18
  - 19
  - 20
  - 21
  - 22
  - 23
notes:
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-C6 USB port'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-C6-MINI-1 or -1U module built on the ESP32-C6FH4 chip, 4 MB flash
  integrated in the chip package; no PSRAM
- Addressable RGB LED on GPIO8
- Wi-Fi 6 / BLE 5 / Zigbee 3.0 / Thread 1.3 (802.15.4)
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=17 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J1+J3 break
  out 22 pads total (quoted from the user guide pin tables: J1 = GPIO 0-8,14; J3
  = GPIO 9,12-13,15-23). Subtracting esp32-c6''s soc.reserved_pins that are exposed
  -- strapping {8,9,15} exposed out of {8,9,10,11,15} (3) and usb_flash_tied {12,13}
  (2) -- gives 22 - 3 - 2 = 17. Math not vendor-stated; verify before treating as
  exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitm-1/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitm-1/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitm-1/user_guide.html
  verified: '2026-08-26'
---

# ESP32-C6-DevKitM-1

Compact ESP32-C6-MINI-1 board with dual USB-C (UART bridge + native USB) and a GPIO8 addressable RGB LED.
