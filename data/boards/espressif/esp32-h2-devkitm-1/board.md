---
id: esp32-h2-devkitm-1
type: board
brand: espressif
name: ESP32-H2-DevKitM-1
soc: esp32-h2
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_free: 14
  gpio_pins:
  - 0
  - 1
  - 2
  - 3
  - 4
  - 5
  - 8
  - 9
  - 10
  - 11
  - 12
  - 13
  - 14
  - 22
  - 23
  - 24
  - 25
  - 26
  - 27
notes:
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-H2 USB port (USB
  2.0 full speed, up to 12 Mbps)'
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-H2-MINI-1 or -1U module, 4 MB flash integrated in the chip package;
  no PSRAM
- Addressable RGB LED on GPIO8
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=14 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J1+J3 break
  out all 19 pads on the chip (quoted from the user guide pin tables: J1 = GPIO 0-5,13-14;
  J3 = GPIO 8-12,22-27). Subtracting esp32-h2''s soc.reserved_pins that are exposed
  -- strapping {8,9,25} (3) and usb_flash_tied {26,27} (2) -- gives 19 - 3 - 2 = 14.
  Math not vendor-stated; verify before treating as exact.'
download_mode:
  mode: manual
  steps: Holding down Boot and then pressing Reset initiates Firmware Download mode
    for downloading firmware through the serial port
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-08-26'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-09-01'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
  verified: '2026-09-01'
---

# ESP32-H2-DevKitM-1

Compact ESP32-H2-MINI-1 board with dual USB-C (UART bridge + native USB) and a GPIO8 addressable RGB LED.
