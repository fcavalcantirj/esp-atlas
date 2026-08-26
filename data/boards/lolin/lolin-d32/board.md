---
id: lolin-d32
type: board
brand: lolin
name: LOLIN D32
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 57
- 25.4
usb:
  bridge: ch340
power:
  battery_connector: true
  charging: true
io:
  gpio_exposed: 22
  gpio_free: 17
notes:
- Espressif ESP32-WROOM-32 module, REV1; 4 MB flash
- Built-in LED on GPIO5
- Lithium battery interface, PH-2.0 2-pin connector, 500 mA max charging current,
  supports 3.7 V LiPo
- Physical USB connector shape not stated on the official page (omitted)
- 'Weight: 6.1 g'
- Plain ESP32-WROOM-32 module (single ordering code, no R-suffix) never had a PSRAM variant
- 'io.gpio_exposed=22 QUOTED: vendor page Technical specs table states "Digital
  I/O Pins | 22". The 500 mA figure on this page is LiPo charging current, not a
  GPIO/rail output rating, so power_out is omitted'
- 'io.gpio_free=17 DERIVED: the vendor''s own labeled pinout diagram (mischianti.org
  reproduction of the wemos.cc silkscreen) enumerates 25 header GPIO pads (VP/36,
  VN/39, 34, 32, 33, 25, 26, 27, 14, 12, 13, 23, 22, GPIO1/TXD0, GPIO3/RXD0, 21,
  19, 18, 5, 17, 16, 4, 0, 2, 15); the vendor''s own "22" figure nets out the 3
  input-only pads among them (34, 36, 39), confirming the 25-pad enumeration.
  Of esp32''s soc.reserved_pins, strapping 0/2/5/12/15 are all exposed (5 pins,
  GPIO5 also the onboard BUILTIN_LED per the official arduino-esp32 d32/pins_arduino.h);
  input_only 34/36/39 are exposed (3 pins, already netted out of the vendor''s 22);
  usb_flash_tied 6/7/8 are not on the header; GPIO35 (VBAT divider, confirmed by
  the same pins_arduino.h) is not exposed, so no separate onboard subtraction is
  needed -- 25 total pads - 5 strapping - 3 input-only = 17'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/d32/d32.html
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-wroom-32_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/d32/d32.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://mischianti.org/wp-content/uploads/2022/10/ESP32-WeMos-LOLIN-D32-pinout-mischianti.png
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/espressif/arduino-esp32/blob/master/variants/d32/pins_arduino.h
  verified: '2026-08-26'
---

# LOLIN D32

ESP32-WROOM-32 devkit with a LiPo battery/charging interface (PH-2.0, 500 mA max), CH340 USB-UART bridge, GPIO5 LED.
