---
id: esp32-s2-saola-1
type: board
brand: espressif
name: ESP32-S2-Saola-1
soc: esp32-s2
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
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
- Single micro-USB port for power, flashing and UART communication
- Bridge chip model not named in the official user guide (omitted)
- EOL/legacy board; guide's worked example uses ESP32-S2-WROVER, 4 MB flash, 2 MB
  PSRAM, but board also supports WROVER-I/WROOM/WROOM-I module variants (fixed
  spec omitted since it varies by module fitted)
- Addressable RGB LED (WS2812) on GPIO18
- Dimensions only in a separate Dimensions PDF (omitted)
- 'io.gpio_free=32 DERIVED, not quoted (SPEC-io-power.md §5.3). Headers J2+J3 break
  out 37 pads total (quoted from the user guide pin tables: J2 = GPIO 0-17; J3 =
  GPIO 18-21,26,33-46). Subtracting esp32-s2''s soc.reserved_pins that are exposed
  -- strapping {0,45,46} (GPIO46 also listed under input_only, so counted once)
  and usb_flash_tied {19,20} -- 5 unique reserved pins exposed -- gives 37 - 5 =
  32. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html
  verified: '2026-08-26'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html
  verified: '2026-08-26'
---

# ESP32-S2-Saola-1

Small ESP32-S2 board (EOL) with a single micro-USB port and a GPIO18 addressable RGB LED; most I/O broken out to dual headers.
