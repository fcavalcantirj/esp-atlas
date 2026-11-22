---
id: firebeetle-esp32
type: board
brand: dfrobot
name: DFRobot FireBeetle ESP32
aka:
- firebeetle32
soc: esp32
flash_mb: 16
psram_mb: 0
form_factor: firebeetle
price_tier: cheap
dimensions_mm:
- 29
- 58
usb:
  bridge: ch340
usb_serial: ch340
power:
  battery_connector: true
  charging: true
extras:
- sd-card
io:
  gpio_exposed: 21
  gpio_free: 11
notes:
- 16 MB flash, 520 KB SRAM
- CH340 USB-to-serial bridge (driver install required)
- Onboard microSD slot
- Dual-Core ESP-WROOM-32 module
- ESP32-WROOM-32/32D/32U modules only ever shipped in non-PSRAM ordering codes (no
  R-suffix variant exists in Espressif's datasheets)
- 'io.gpio_exposed=21 DERIVED (SPEC-io-power.md §5.3), not vendor-quoted: the vendor
  page states only "Digital I/O: 10 (default setting of arduino)", which undercounts
  by omitting D10/GPIO0 (a strapping pin) and the A0-A5/SDA/SCL pins from that one
  spec line. The full exposed set is taken from the official Espressif Arduino core
  variant for this exact board (arduino-esp32 variants/firebeetle32/pins_arduino.h:
  D0-D10, SDA, SCL, MOSI/MISO/SCK, A0-A5), cross-checked against the DFR0478 schematic''s
  P1/P2 header labels (D2-D9, SDA/SCL/SCK all present): {0,1,2,3,5,9,10,13,15,18,19,21,22,23,25,26,27,34,35,36,39}
  -- 21 unique GPIOs.'
- 'io.gpio_free=11 DERIVED (SPEC-io-power.md §5.3): subtracting esp32''s soc.reserved_pins
  that are exposed -- strapping {0,2,5,15}: all 4 present; input_only {34,35,36,39}:
  all 4 present (ADC-only, cannot be used as general digital I/O); usb_flash_tied
  {9,10}: both present (2 of the 6 flash-tied pins are broken out as D5/D6 on this
  board) -- gives 21 - 4 - 4 - 2 = 11. Math not vendor-stated; verify before treating
  as exact.'
- usb_serial derived from usb.bridge (ch340)
getting_started: https://wiki.dfrobot.com/dfr0478
images:
  pinout: https://dfimg.dfrobot.com/62fba4cb025a892c98c6da64/wikien/555ad7fa66fecc61fe288e251ac267ce_0x0.png.webp
platformio_definitions:
- id: firebeetle32
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 283bf71fe7424b698f0cac831afdbc5ad7a44265ade72e8bda7387a29b7539b9
- id: firebeetle32
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 0e44ddb1ec1aef14498f8991837860475cd4b8bb0db324d3386e4847ded9e97a
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0478/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-wroom-32d_esp32-wroom-32u_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/master/variants/firebeetle32/pins_arduino.h
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://dfimg.dfrobot.com/wiki/19339/DFR0478_firebeetle-esp32-board_schematics_V4.0.pdf
  verified: '2026-08-26'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-07'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/firebeetle32.json
  verified: '2026-09-07'
- field: usb_serial
  url: https://wiki.dfrobot.com/dfr0478/
  verified: '2026-09-07'
- field: getting_started
  url: https://wiki.dfrobot.com/dfr0478
  verified: '2026-09-11'
- field: images.pinout
  url: https://dfimg.dfrobot.com/62fba4cb025a892c98c6da64/wikien/555ad7fa66fecc61fe288e251ac267ce_0x0.png.webp
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/firebeetle32.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/firebeetle32.json
  verified: '2026-11-22'
---

# DFRobot FireBeetle ESP32

Original low-power FireBeetle main board on the ESP-WROOM-32 module: 16 MB flash, CH340 USB-serial bridge, onboard microSD slot, and Li-ion battery charging.
