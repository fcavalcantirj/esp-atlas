---
id: esp-wrover-kit
type: board
brand: espressif
name: ESP-WROVER-KIT
soc: esp32
psram_mb: 8
form_factor: devkit
price_tier: medium
usb:
  connector: micro-usb
  bridge: ft2232hl
extras:
- rgb-led
io:
  gpio_free: 13
  gpio_pins:
  - 0
  - 2
  - 4
  - 5
  - 12
  - 13
  - 14
  - 15
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
- USB 2.0 A-to-Micro-B cable; FT2232HL provides both the UART bridge and on-board
  JTAG debugging
- Carries an ESP32-WROVER-E module with 64-Mbit (8 MB) PSRAM
- Four diagnostic red LEDs on FT2232HL GPIOs, plus a red 5V Power-On LED and an RGB
  LED (GPIO0/GPIO2/GPIO4)
- Dimensions not provided in the user guide (omitted)
- io.gpio_free=13 DERIVED, not quoted (SPEC-io-power.md §5.3). Main I/O connector
  JP1 lists 24 pads in its table, but the user guide states "GPIO16 and GPIO17 ...
  are not broken out to the board's pin headers" (reserved for PSRAM CS/CLK on the
  WROVER module) -- excluding those 2 leaves 22 usable exposed pads (GPIO 0,2,4,5,12-15,18,19,21-23,25-27,32-36,39).
  Subtracting esp32's soc.reserved_pins that are exposed -- strapping {0,2,5,12,15}
  (5) and input_only {34,35,36,39} (4); usb_flash_tied {6-11} none exposed -- gives
  22 - 5 - 4 = 13. Math not vendor-stated; verify before treating as exact.
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
  verified: '2026-08-26'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
  verified: '2026-09-01'
---

# ESP-WROVER-KIT

ESP32-WROVER-E development/debug board with a built-in FT2232HL JTAG debugger and an onboard RGB LED.
