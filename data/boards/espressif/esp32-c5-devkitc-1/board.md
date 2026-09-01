---
id: esp32-c5-devkitc-1
type: board
brand: espressif
name: ESP32-C5-DevKitC-1
soc: esp32-c5
form_factor: devkit
usb:
  connector: usb-c
extras:
- rgb-led
download_mode:
  mode: manual
  steps: 'Hold down Boot, then press Reset, then release Boot to enter Firmware
    Download mode'
  note: 'Two USB-C ports: the USB-to-UART port for serial flashing, or the native
    ESP32-C5 USB port (USB-Serial-JTAG).'
usb_serial: native-usb-serial-jtag
io:
  gpio_free: 12
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
  - 23
  - 24
  - 25
  - 26
  - 27
  - 28
notes:
- 'Board version documented: v1.2'
- 'Carries an ESP32-C5-WROOM-1(U) module (module record not yet in the atlas);
  modeled via soc: esp32-c5 rather than module: per the current data model -- cpu/radio
  specs come straight from the ESP32-C5 chip record, not restated here'
- 'Two USB Type-C ports: a UART-bridge port and the native ESP32-C5 USB 2.0 full-speed
  port; USB-UART bridge chip not named on the page (just "single-chip USB-to-UART
  bridge")'
- Addressable RGB LED on GPIO27
- J3 pin 6 is NC/GPIO15 depending on whether the module variant integrates SPI PSRAM
  (SPICS1 when PSRAM is present); excluded from gpio_pins/gpio_free as not guaranteed
  available
- Flash/PSRAM size not stated on this user-guide page -- omitted rather than guessed
- 'io.gpio_free=12 DERIVED, not quoted (SPEC-io-power.md §5.3). J1+J3 headers break
  out 21 definite GPIOs per the pin tables (J1: 0,1,2,3,6,7,8,9,10,25,26; J3: 4,5,11,12,13,14,23,24,27,28
  -- GPIO15 excluded as conditional). Subtracting esp32-c5''s soc.reserved_pins that
  are exposed -- strapping {2,3,7,25,26,27,28} (7) and usb_flash_tied {13,14} (2)
  -- gives 21 - 7 - 2 = 12. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html
  verified: '2026-08-28'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html
  verified: '2026-08-28'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html
  verified: '2026-08-28'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html
  verified: '2026-09-01'
- field: usb_serial
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html
  verified: '2026-09-01'
---

# ESP32-C5-DevKitC-1

Entry-level ESP32-C5-WROOM-1(U) devkit with dual USB-C (UART bridge + native) and a GPIO27 addressable RGB LED. First Espressif devkit with 5 GHz Wi-Fi 6.
