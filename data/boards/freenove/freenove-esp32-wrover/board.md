---
id: freenove-esp32-wrover
type: board
brand: freenove
name: ESP32-WROVER
aka:
- freenove_esp32_wrover
soc: esp32
usb:
  bridge: ch340
usb_serial: ch340
notes:
- The board shipped in Freenove's ESP32-WROVER kits (FNK0060). Freenove's Preface says
  "the ESP32-WROVER is designed based on the PCB on-board antenna-packaged ESP32-WROVER
  module" and "ESP32 uses CH340 to download codes"
- 'Onboard resources per the Preface: GPIO pins, LED indicator, camera interface, reset
  button and boot mode selection button, USB port'
- Two board revisions exist; Freenove says "The version on the left is no longer
  mass-produced, and we mainly maintain the version on the right"
- The exact WROVER module variant, flash, PSRAM, USB connector type and dimensions are
  not stated in Freenove's text (omitted)
- aka "freenove_esp32_wrover" is the board id in the pioarduino PlatformIO platform
- Not the Freenove ESP32-WROOM board (FNK0090) or the Freenove ESP32-S3-WROOM board,
  which are separate products
getting_started: https://docs.freenove.com/projects/fnk0060/en/latest/
images:
  pinout: https://raw.githubusercontent.com/Freenove/Freenove_ESP32_WROVER_Board/main/ESP32_Pinout_V3.0.png
platformio_definitions:
- id: freenove_esp32_wrover
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 9dc89702b75afb7b2eb39382ab87d8962dcc6480eba8a139db7fb6d4b13f35ea
- id: freenove_esp32_wrover
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 3758b9bbdfe97e61e7bb2309db0b0f0cfa58476522b1aadfa41adc20d3736916
sources:
- field: '*'
  url: https://github.com/Freenove/Freenove_ESP32_WROVER_Board
  verified: '2026-11-17'
- field: soc
  url: https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html
  verified: '2026-11-17'
- field: usb.bridge
  url: https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html
  verified: '2026-11-17'
- field: usb_serial
  url: https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html
  verified: '2026-11-17'
- field: notes
  url: https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html
  verified: '2026-11-17'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/freenove_esp32_wrover.json
  verified: '2026-11-17'
- field: getting_started
  url: https://docs.freenove.com/projects/fnk0060/en/latest/
  verified: '2026-11-17'
- field: images.pinout
  url: https://raw.githubusercontent.com/Freenove/Freenove_ESP32_WROVER_Board/main/ESP32_Pinout_V3.0.png
  verified: '2026-11-17'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/freenove_esp32_wrover.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/freenove_esp32_wrover.json
  verified: '2026-11-22'
---

# Freenove ESP32-WROVER

Freenove's ESP32 development board built on the PCB-antenna ESP32-WROVER module, with
a CH340 USB-to-serial bridge for flashing and a camera interface. It is the board
inside Freenove's ESP32-WROVER starter kits.
