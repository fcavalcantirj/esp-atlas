---
id: esp32-s2-devkitm-1
type: board
brand: espressif
name: ESP32-S2-DevKitM-1
aka:
- ESP32-S2-DevKitM-1-N4R2
- ESP32-S2-DevKitM-1R
soc: esp32-s2
flash_mb: 4
form_factor: devkit
dimensions_mm:
- 54.0
- 25.4
usb:
  connector: micro-usb
  bridge: cp2102n
extras:
- rgb-led
io:
  gpio_free: 32
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
  - 20
  - 21
  - 26
  - 33
  - 34
  - 35
  - 36
  - 37
  - 38
  - 39
  - 40
  - 41
  - 42
  - 43
  - 44
  - 45
  - 46
notes:
- Single micro-USB port (power and communication via the on-board USB-to-UART bridge);
  the schematic names the bridge CP2102N-A02-GQFN28
- 'Ordering variants with the PCB antenna: ESP32-S2-DevKitM-1-N4R2 (ESP32-S2-MINI-2,
  4 MB flash, 2 MB PSRAM, recommended), ESP32-S2-DevKitM-1 (EOL, ESP32-S2-MINI-1,
  4 MB flash, no PSRAM) and ESP32-S2-DevKitM-1R (EOL, ESP32-S2-MINI-1, 4 MB flash,
  2 MB PSRAM); psram_mb omitted since it varies by SKU'
- The ESP32-S2-DevKitM-1U / -1U-N4R2 / -1RU variants carry an external antenna connector
  and are separate SKUs (not this record)
- Addressable RGB LED on GPIO18
- Dimensions 54.00 x 25.40 mm board outline, from the ESP32-S2-DevKitM-1 V1 Dimensions
  PDF
- 'io.gpio_free=32 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J1+J3 break
  out 37 pads total (quoted from the user guide pin tables: J1 = GPIO 0-17; J3 = GPIO
  18-21,26,33-46). Subtracting esp32-s2''s soc.reserved_pins that are exposed -- strapping
  {0,45,46} (GPIO46 also listed under input_only, so counted once) and usb_flash_tied
  {19,20} -- 5 unique reserved pins exposed -- gives 37 - 5 = 32. GPIO18 (RGB LED)
  is not subtracted. Math not vendor-stated; verify before treating as exact.'
download_mode:
  mode: manual
  steps: Holding down Boot and then pressing Reset initiates Firmware Download mode
    for downloading firmware through the serial port
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
images:
  photo: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/_images/esp32-s2-devkitm-1-v1-isometric.png
  pinout: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/_images/esp32-s2-devkitm-1-v1-pin-layout.png
usb_serial: cp2102n
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
- field: dimensions_mm
  url: https://dl.espressif.com/dl/schematics/ESP32-S2-DevKitM-1_V1_Dimensions.pdf
  verified: '2026-11-15'
- field: usb.bridge
  url: https://dl.espressif.com/dl/schematics/ESP32-S2-DevKitM-1_V1_Schematics.pdf
  verified: '2026-11-15'
- field: usb_serial
  url: https://dl.espressif.com/dl/schematics/ESP32-S2-DevKitM-1_V1_Schematics.pdf
  verified: '2026-11-15'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
- field: images
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitm-1/user_guide.html
  verified: '2026-11-15'
---

# ESP32-S2-DevKitM-1

Small ESP32-S2-MINI module board with a micro-USB CP2102N UART bridge and a GPIO18 addressable RGB LED.
