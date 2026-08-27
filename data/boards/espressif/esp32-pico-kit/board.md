---
id: esp32-pico-kit
type: board
brand: espressif
name: ESP32-PICO-KIT
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 52
- 20.3
- 10
usb:
  connector: micro-usb
io:
  gpio_free: 19
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
  - 37
  - 38
  - 39
notes:
- Micro-USB UART-bridge port; bridge chip is CP2102 on v4 (up to 1 Mbps) or CP2102N
  on v4.1 (up to 3 Mbps) — version-dependent, so usb.bridge left unset
- Built around the ESP32-PICO-D4 SiP (complete ESP32 system including 4 MB flash);
  no PSRAM
- Single red 5V Power-On LED
- 'io.gpio_free=19 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J2+J3 break
  out all 34 pads on the chip (quoted from the user guide pin tables: J2 = GPIO
  1,3,5-10,18,19,21-23,34,35,37,38; J3 = GPIO 0,2,4,11-17,25-27,32,33,36,39). Subtracting
  esp32''s soc.reserved_pins that are exposed -- strapping {0,2,5,12,15} (5), input_only
  {34,35,36,39} (4), and usb_flash_tied {6,7,8,9,10,11} (6) -- gives 34 - 5 - 4
  - 6 = 19. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-pico-kit/user_guide.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-pico-kit/user_guide.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-pico-kit/user_guide.html
  verified: '2026-08-26'
---

# ESP32-PICO-KIT

Small ESP32-PICO-D4 SiP board (52 x 20.3 x 10 mm) with a single micro-USB UART-bridge port.
