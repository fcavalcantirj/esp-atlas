---
id: sparkfun-iot-redboard-esp32
type: board
brand: sparkfun
name: SparkFun IoT RedBoard - ESP32 Development Board
soc: esp32
psram_mb: 0
form_factor: devkit
price_tier: medium
dimensions_mm:
- 58.4
- 68.6
usb:
  connector: usb-c
  bridge: ch340g
power:
  battery_connector: true
  charging: true
extras:
- qwiic
- sd-card
- rgb-led
io:
  gpio_exposed: 24
  gpio_free: 17
notes:
- ESP32-D0WD-V3; module flash configurable at 4/8/16 MB per product page (default shipped capacity not stated)
- Battery charging via onboard MCP73831 (500mA default), JST connector for single-cell LiPo; onboard MAX17048 fuel gauge
- Arduino Uno-compatible form factor ("RedBoard" line) with Qwiic connector and microSD slot
- ESP32-D0WD-V3 chip variant has no PSRAM per Espressif's ESP32 series ordering table
- 'io.gpio_exposed=24 DERIVED: the vendor''s own Fritzing part file (linked from
  the GitHub hardware repo) enumerates the header nets by GPIO: 1(RXD0/TXD0 pair
  gives 1,3), 3, 4, 5(!CS!), 12(TDI), 13(TCK, also re-broken-out as a second header
  pad), 14(TMS, also re-broken-out), 15(TDO), 16, 17, 18(SCK), 19(POCI/MISO),
  21(SDA), 22(SCL), 23(PICO/MOSI), 25, 26, 27, and ADC1 channels 0/3/4/5/6/7 (=32/33/34/35/36/39)
  -- 24 distinct GPIOs; no vendor-stated total pin count exists on the product
  page or hookup guide to cross-check against. GPIO2 drives the onboard WS2812
  RGB LED per the espressif/arduino-esp32 board variant (RGB_LED_PIN 2) and is
  not a header net in the Fritzing part, so it is excluded from the 24 already;
  GPIO0 is likewise absent from the Fritzing header nets'
- 'io.gpio_free=17 DERIVED: of esp32''s soc.reserved_pins, strapping 5/12/15 are
  exposed (3 pins; 0 and 2 are not header nets per the Fritzing part above);
  input_only 34/35/36/39 are exposed (4 pins); usb_flash_tied 6/7/8 are not on
  the header. 24 total - 3 strapping - 4 input-only = 17'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-iot-redboard-esp32-development-board.html
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/iot-redboard-esp32-development-board-hookup-guide/all
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://github.com/sparkfun/Fritzing_Parts/blob/main/products/19177_sfe_iot_redboard_esp32_development_board.fzpz
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://github.com/espressif/arduino-esp32/blob/master/variants/sparkfun_esp32_iot_redboard/pins_arduino.h
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/sparkfun/Fritzing_Parts/blob/main/products/19177_sfe_iot_redboard_esp32_development_board.fzpz
  verified: '2026-08-26'
---

# SparkFun IoT RedBoard - ESP32 Development Board

An Arduino Uno-shaped ESP32 devkit in SparkFun's RedBoard line, with USB-C (CH340G bridge), Qwiic connector, microSD slot, addressable RGB status LED, and onboard LiPo charging with fuel gauge.
