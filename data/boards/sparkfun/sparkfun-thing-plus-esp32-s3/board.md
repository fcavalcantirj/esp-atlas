---
id: sparkfun-thing-plus-esp32-s3
type: board
brand: sparkfun
name: SparkFun Thing Plus - ESP32-S3
aka:
- SparkFun ESP32-S3 Thing Plus
- SPARKFUN_ESP32S3_THING_PLUS
- sparkfun_esp32s3_thing_plus
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: thing-plus
dimensions_mm:
- 58.42
- 22.86
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
extras:
- qwiic
- sd-card
- rgb-led
io:
  gpio_exposed: 21
  gpio_free: 21
  gpio_pins:
  - 1
  - 2
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
  - 21
  - 42
  - 43
  - 44
notes:
- 'SparkFun SKU WRL-24408: the product page reads "SKU: WRL-24408"'
- 'ESP32-S3-MINI-1-N4R2 module (4 MB flash, 2 MB PSRAM): the hookup guide reads "This
  Thing Plus uses the ESP32-S3-MINI1-N4R2 which features 4MB Quad SPI Flash memory and
  2MB of PSRAM (Pseudo-static RAM)." The schematic labels the module ESP32-S3-MINI-1-N4R2.
  soc is referenced directly because the catalog has no esp32-s3-mini-1 module record'
- 'usb.bridge=native DERIVED: the hookup guide says the USB-C connector "connects directly
  to the ESP32-S3''s USB serial converter" and that the ESP32-S3 "does not need any external
  UART-to-USB conversion"; the schematic routes the USB-C D+/D- lines as ESP20/D+ and ESP19/D-
  to the module with no bridge IC. usb_serial derived from usb.bridge (native) + soc usb.type
  serial-jtag'
- 'Battery: a 2-pin JST LiPo connector; the hookup guide reads "It also has an MCP73831
  battery charger to charge an attached battery and a MAX17048 fuel gauge to monitor battery
  voltage levels."'
- 'Qwiic connector on "IO8/SDA and IO9/SCL"; microSD slot that "connects to the ESP32-S3''s
  SDIO-4 pins"; addressable LED: "The WS2812 RGB LED connects the LED''s Data In signal
  to IO46."'
- 'Peripheral power: a second RT9080 3.3V regulator feeds the 3.3V_P rail (Qwiic, fuel
  gauge pull-ups); "The RT9080''s EN (Enable) pin is tied to ESP45 so users can drive it
  LOW in their code to disable this line."'
- 'Buttons: RESET and BOOT; "The BOOT button puts the ESP32-S3 into bootloader mode when
  held down during power on or reset."'
- 'dimensions_mm QUOTED: the hookup guide gives the board as "(58.42mm x 22.86mm)", matching
  SparkFun''s official dimension drawing (2.3000 in x 0.9000 in). The product page''s 2.55
  in length disagrees with both and is not used'
- 'io.gpio_exposed=21 QUOTED: the hookup guide''s PTH headers "break out a selection of
  21 GPIO pins from the ESP32-S3"'
- 'io.gpio_pins: the schematic''s ThingPlus header symbol and the dimension drawing''s
  silkscreen enumerate the same 21 GPIOs: 43, 44, 8, 9, 13, 11, 12, 10, 14, 15, 16, 17,
  18 (TX, RX, SDA, SCL, POCI, PICO, SCK, A0-A5) and 21, 7, 6, 5, 4, 2, 1, 42'
- 'io.gpio_free=21 DERIVED: of esp32-s3''s soc.reserved_pins, strapping 0/3/45/46 and
  usb_flash_tied 19/20/35/36/37 are not on the headers (0 drives the STAT LED, 45 the
  RT9080 enable, 46 the WS2812, 19/20 the USB-C port, all onboard), so no subtraction
  applies: 21 - 0 = 21'
getting_started: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/
platformio_definitions:
- id: sparkfun_esp32s3_thing_plus
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 338527a1ad69af6d41dd50a1539ca5ae9719a31f51affcd088548a9df9672af8
- id: sparkfun_esp32s3_thing_plus
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 97f4c7e9294325d566b7e344c260a241b07df02790f4f515e3e0063c3bc12382
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-thing-plus-esp32-s3.html
  verified: '2026-11-20'
- field: '*'
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: soc
  url: https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf
  verified: '2026-11-20'
- field: flash_mb
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: psram_mb
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: dimensions_mm
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: dimensions_mm
  url: https://cdn.sparkfun.com/assets/4/f/e/7/b/SparkFun_Thing_Plus_ESP32-S3-Dimensions.jpg
  verified: '2026-11-20'
- field: usb.connector
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: usb.bridge
  url: https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf
  verified: '2026-11-20'
- field: usb.bridge
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: usb_serial
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: power
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: extras
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: io.gpio_exposed
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/hardware_overview/
  verified: '2026-11-20'
- field: io.gpio_pins
  url: https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf
  verified: '2026-11-20'
- field: io.gpio_pins
  url: https://cdn.sparkfun.com/assets/4/f/e/7/b/SparkFun_Thing_Plus_ESP32-S3-Dimensions.jpg
  verified: '2026-11-20'
- field: io.gpio_free
  url: https://cdn.sparkfun.com/assets/5/e/6/5/0/SparkFun_Thing_Plus_ESP32-S3.pdf
  verified: '2026-11-20'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-11-20'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/sparkfun_esp32s3_thing_plus.json
  verified: '2026-11-20'
- field: getting_started
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32-S3/
  verified: '2026-11-20'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/sparkfun_esp32s3_thing_plus.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/sparkfun_esp32s3_thing_plus.json
  verified: '2026-11-22'
---

# SparkFun Thing Plus - ESP32-S3

Feather-footprint ESP32-S3 board built on the ESP32-S3-MINI-1-N4R2 module (4 MB flash, 2 MB PSRAM), with USB-C wired straight to the chip's native USB, a 2-pin JST LiPo connector with MCP73831 charging and a MAX17048 fuel gauge, a Qwiic connector, a microSD slot on the SDIO bus, and a WS2812 RGB LED.
