---
id: esp32-devkitm-1
type: board
brand: espressif
name: ESP32-DevKitM-1
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
io:
  gpio_free: 17
  gpio_pins:
  - 0
  - 1
  - 2
  - 3
  - 4
  - 5
  - 9
  - 10
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
  - 37
  - 38
  - 39
notes:
- Single micro-USB (power/flash/comms via on-board USB-to-UART bridge); classic
  ESP32 has no native USB
- Bridge chip model not named in the official user guide (omitted)
- Carries ESP32-MINI-1 or -1U SiP module, 4 MB flash integrated in the chip package;
  no PSRAM
- Boards manufactured before 2021-12-02 may carry a single-core module variant
- Dimensions not provided in the user guide (omitted)
- 'io.gpio_free=17 DERIVED, not quoted (SPEC-io-power.md §5.3). The user guide''s
  Pin Description table breaks out 28 pads total (quoted: GPIO 0-5,9-10,12-15,18-19,21-23,25-27,32-39).
  Subtracting esp32''s soc.reserved_pins that are exposed -- strapping {0,2,5,12,15}
  (5), input_only {34,35,36,39} (4), and usb_flash_tied {9,10} exposed out of {6,7,8,9,10,11}
  (2) -- gives 28 - 5 - 4 - 2 = 17. Math not vendor-stated; verify before treating
  as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitm-1/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitm-1/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitm-1/user_guide.html
  verified: '2026-08-26'
---

# ESP32-DevKitM-1

Compact ESP32-MINI-1 SiP board with a single micro-USB UART-bridge port.
