---
id: sparkfun-thing-plus-esp32-s2-wroom
type: board
brand: sparkfun
name: SparkFun Thing Plus - ESP32-S2 WROOM
soc: esp32-s2
flash_mb: 4
psram_mb: 0
form_factor: thing-plus
price_tier: medium
dimensions_mm:
- 64.77
- 22.86
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- qwiic
io:
  gpio_exposed: 21
  gpio_free: 21
notes:
- ESP32-S2 WROOM module; 4 MB flash
- Battery charging via onboard MCP73831 charger, JST connector for single-cell LiPo
- ESP32-S2 omits Bluetooth and 5GHz WiFi; WiFi 802.11b/g/n only
- Thing Plus form factor is pin-compatible with the Adafruit Feather footprint
- ESP32-S2-WROOM (as opposed to -WROVER) has no PSRAM, per Espressif's ESP32-S2-WROOM datasheet
- 'io.gpio_exposed=21 QUOTED: vendor hookup guide hardware overview states "There
  are 21 I/O pins broken out on this board, with 8 I/O pads on the back of the
  board" -- the 21 front-header count is used; the 8 back pads are not header
  pins and are not added in'
- 'io.gpio_free=21 DERIVED: the vendor''s own graphical datasheet enumerates the
  21 front-header GPIOs by number (1,2,4,6,8,10,11,12,13 on the left header;
  3,34,33,37,35,36,5,7,9,14,18,17 on the right), matching the "21" front-header
  count exactly. Of esp32-s2''s soc.reserved_pins, strapping 0/45/46 are not on
  this header; input_only 46 is not on this header; usb_flash_tied 19/20 are
  not on this header (both consumed internally by the native USB-C port) --
  none of the reserved pins are exposed, so no subtraction applies: 21 - 0 = 21'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-thing-plus-esp32-s2-wroom.html
  verified: '2026-08-22'
- field: dimensions_mm
  url: https://learn.sparkfun.com/tutorials/esp32-s2-thing-plus-hookup-guide/all
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-s2-wroom_esp32-s2-wroom-i_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://learn.sparkfun.com/tutorials/esp32-s2-thing-plus-hookup-guide/hardware-overview
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://cdn.sparkfun.com/assets/d/b/4/3/e/graphical_datasheet_ESP32-S2_thing_plus.pdf
  verified: '2026-08-26'
---

# SparkFun Thing Plus - ESP32-S2 WROOM

Feather-footprint-compatible ESP32-S2 board with USB-C, Qwiic connector, and onboard LiPo charging. The single-core ESP32-S2 module trades Bluetooth and 5GHz WiFi for extra security features (AES-XTS flash/RAM encryption, RSA-PSS secure boot) and native USB.
