---
id: esp32-s3-devkitc-1
type: board
brand: espressif
name: ESP32-S3-DevKitC-1
aka:
- esp32-s3-devkitc-1-n32r8v
- esp32-s3-devkitc1-n16r16
- esp32-s3-devkitc1-n16r2
- esp32-s3-devkitc1-n16r8
- esp32-s3-devkitc1-n4r2
- esp32-s3-devkitc1-n4r8
- esp32-s3-devkitc1-n8r2
- esp32-s3-devkitc1-n8r8
module: esp32-s3-wroom-1
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: medium
usb:
  connector: micro-usb
power:
  battery_connector: false
  charging: false
extras:
- rgb-led
io:
  gpio_free: 27
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
  - 47
  - 48
notes:
- 'Two micro-USB: a UART-bridge port and the native ESP32-S3 full-speed USB OTG port'
- Addressable RGB LED (GPIO38 on v1.1, GPIO48 on v1.0)
- Carries ESP32-S3-WROOM-1/-1U/-2; fixed here to esp32-s3-wroom-1
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=27 DERIVED, not quoted (SPEC-io-power.md §5.3). Header J1+J3 break
  out 36 pads total (quoted from the user guide pin tables: J1 = GPIO 3-18,46; J3
  = GPIO 0-2,19-21,35-45,47,48). Subtracting esp32-s3''s soc.reserved_pins that are
  exposed -- strapping {0,3,45,46} (4) and usb_flash_tied {19,20,35,36,37} (5) --
  gives 36 - 4 - 5 = 27. Math not vendor-stated; verify before treating as exact.'
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
download_mode:
  mode: manual
  steps: Holding down Boot and then pressing Reset initiates Firmware Download mode
    for downloading firmware through the serial port
usb_serial: usb-uart-bridge-unspecified
images:
  photo: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/_images/esp32-s3-devkitc-1-v1.1-isometric.png
  pinout: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/_images/ESP32-S3_DevKitC-1_pinlayout_v1.1.jpg
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-08-21'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-08-26'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc-1.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc-1-n32r8v.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n16r16.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n16r2.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n16r8.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n4r2.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n4r8.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n8r2.json
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-s3-devkitc1-n8r8.json
  verified: '2026-09-07'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-09-07'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-09-10'
- field: usb_serial
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-09-10'
- field: images
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
  verified: '2026-09-10'
---

# ESP32-S3-DevKitC-1

ESP32-S3-WROOM-1 dev board with two micro-USB ports (UART bridge + native USB OTG) and an addressable RGB LED.
