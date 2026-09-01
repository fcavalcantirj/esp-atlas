---
id: esp32-c6-devkitc-1
type: board
brand: espressif
name: ESP32-C6-DevKitC-1
module: esp32-c6-wroom-1
flash_mb: 8
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: usb-c
power:
  battery_connector: false
  charging: false
extras:
- rgb-led
io:
  gpio_free: 16
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
- 'Two USB Type-C: a UART-bridge port and the native ESP32-C6 USB 2.0 full-speed port'
- Addressable RGB LED on GPIO8
- Based on ESP32-C6-WROOM-1(U) with 8 MB flash; Wi-Fi 6 / BLE 5 / 802.15.4
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=16 DERIVED, not quoted (SPEC-io-power.md §5.3). Header J1+J3 break
  out 23 pads total (quoted from the user guide pin tables: J1 = GPIO 0-8,10,11; J3
  = GPIO 9,12,13,15-23). Subtracting esp32-c6''s soc.reserved_pins that are exposed
  -- strapping {8,9,10,11,15} (5) and usb_flash_tied {12,13} (2) -- gives 23 - 5 -
  2 = 16. Math not vendor-stated; verify before treating as exact.'
download_mode:
  mode: manual
  steps: Holding down Boot and then pressing Reset initiates Firmware Download mode
    for downloading firmware through the serial port
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-08-21'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-08-26'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-09-01'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html
  verified: '2026-09-01'
---

# ESP32-C6-DevKitC-1

Entry ESP32-C6-WROOM-1 board with dual USB-C (UART bridge + native USB) and a GPIO8 addressable RGB LED.
