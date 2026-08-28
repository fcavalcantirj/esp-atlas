---
id: esp32-c61-devkitc-1
type: board
brand: espressif
name: ESP32-C61-DevKitC-1
soc: esp32-c61
form_factor: devkit
usb:
  connector: usb-c
extras:
- rgb-led
io:
  gpio_free: 15
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
  - 22
  - 23
  - 24
  - 25
  - 26
  - 27
  - 28
  - 29
notes:
- 'Board version documented: v2.0'
- 'Carries an ESP32-C61-WROOM-1 module (module record not yet in the atlas); modeled
  via soc: esp32-c61 rather than module: per the current data model -- cpu/radio
  specs come straight from the ESP32-C61 chip record, not restated here'
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-C61 USB 2.0 full-speed
  port; USB-UART bridge chip not named on the page (just "single USB-to-UART bridge
  chip")'
- Addressable RGB LED on GPIO8
- J1 pin 11 is NC/GPIO14 depending on whether the module variant integrates SPI PSRAM
  (SPICS1 when PSRAM is present); excluded from gpio_pins/gpio_free as not guaranteed
  available
- 'User guide states the ESP32-C61-WROOM-1 module on this board comes with up to
  8 MB SPI flash and 2 MB PSRAM; no fixed value is stated for this specific board,
  so flash_mb/psram_mb are omitted rather than guessed'
- 'io.gpio_free=15 DERIVED, not quoted (SPEC-io-power.md §5.3). J1+J3 headers break
  out 22 definite GPIOs per the pin tables (J1: 0,1,2,3,4,5,6,7,8,29; J3: 9,10,11,12,13,22,23,24,25,26,27,28
  -- GPIO14 excluded as conditional). Subtracting esp32-c61''s soc.reserved_pins
  that are exposed -- strapping {3,4,7,8,9} (5) and usb_flash_tied {12,13} (2) --
  gives 22 - 5 - 2 = 15. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c61/esp32-c61-devkitc-1/user_guide.html
  verified: '2026-08-28'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c61/esp32-c61-devkitc-1/user_guide.html
  verified: '2026-08-28'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c61/esp32-c61-devkitc-1/user_guide.html
  verified: '2026-08-28'
---

# ESP32-C61-DevKitC-1

Entry-level ESP32-C61-WROOM-1 devkit with dual USB-C (UART bridge + native) and a GPIO8 addressable RGB LED. Budget Wi-Fi 6 (2.4 GHz only), no 802.15.4.
