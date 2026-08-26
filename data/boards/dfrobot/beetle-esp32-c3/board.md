---
id: beetle-esp32-c3
type: board
brand: dfrobot
name: DFRobot Beetle ESP32-C3
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: beetle
price_tier: cheap
dimensions_mm:
- 25
- 20.5
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
io:
  gpio_exposed: 13
  gpio_free: 10
notes:
- 4 MB flash
- TP4057 Li-ion charge management chip, max 400 mA
- Ships with a GDI expansion board for display connectivity
- 13 digital I/O ports
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=13 QUOTED: vendor page states "It features 13 digital I/O ports"
  and "Digital I/O | x13"'
- 'io.gpio_free=10 DERIVED (SPEC-io-power.md §5.3): the vendor page never names individual
  pins, so the 13 exposed GPIOs are identified via the official Espressif Arduino
  core variant for this exact board (arduino-esp32 variants/dfrobot_beetle_esp32c3/pins_arduino.h):
  {0,1,2,3,4,5,6,7,8,9,10,20,21} -- 13 unique GPIOs, matching the vendor count exactly.
  Subtracting esp32-c3''s soc.reserved_pins that are exposed -- strapping {2,8,9}:
  all 3 present; usb_flash_tied {18,19}: 0 present (native USB pins are not broken
  out on this board) -- gives 13 - 3 = 10. Math not vendor-stated; verify before
  treating as exact.'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0868/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr0868/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/master/variants/dfrobot_beetle_esp32c3/pins_arduino.h
  verified: '2026-08-26'
---

# DFRobot Beetle ESP32-C3

Coin-sized ESP32-C3 RISC-V board (25 x 20.5 mm): USB-C, 4 MB flash, onboard Li-ion charging, and a bundled GDI expansion board for displays.
