---
id: beetle-esp32-c6
type: board
brand: dfrobot
name: DFRobot Beetle ESP32-C6
soc: esp32-c6
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
  gpio_free: 11
notes:
- 4 MB flash
- TP4057 Li-ion charge management chip, max 0.5 A
- 13 digital I/O ports in a coin-sized form factor
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=13 QUOTED: vendor page states "has 13 IOs" and "Digital I/O
  x13"'
- 'io.gpio_free=11 DERIVED (SPEC-io-power.md §5.3): the vendor page never names
  individual pins as a single table. Cross-referencing the official schematic (P3/P4
  header nets: IO4,IO5,IO6,IO7,IO16,IO17,IO19,IO20,IO21,IO22,IO23 -- 11 pins) with
  the Espressif Arduino core variant (arduino-esp32 variants/dfrobot_beetle_esp32c6/pins_arduino.h:
  LED_BUILTIN=15,TX=16,RX=17,SDA=19,SCL=20,SS=4,MOSI=22,MISO=21,SCK=23) gives a
  12-pin union {4,5,6,7,15,16,17,19,20,21,22,23}; the 13th pin (to match the vendor''s
  stated total) is GPIO9, wired to the onboard BOOT button/pad per DFRobot forum
  discussion of this board''s pinout. Subtracting esp32-c6''s soc.reserved_pins
  that are exposed -- strapping {9,15}: both present; usb_flash_tied {12,13}: 0
  present -- gives 13 - 2 = 11. Math not vendor-stated; verify before treating as
  exact.'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr1117/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr1117/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://dfimg.dfrobot.com/wiki/19405/DFR1117_beetle-esp32-c6_schematics_V1.1.zip
  verified: '2026-08-26'
---

# DFRobot Beetle ESP32-C6

Coin-sized ESP32-C6 board (25 x 20.5 mm) for wearable and smart-home IoT: USB-C, 4 MB flash, onboard Li-ion charging, and 13 digital I/O ports.
