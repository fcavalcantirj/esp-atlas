---
id: sparkfun-thing-plus-esp32-wroom
type: board
brand: sparkfun
name: SparkFun Thing Plus - ESP32 WROOM (USB-C)
soc: esp32
flash_mb: 16
psram_mb: 0
form_factor: thing-plus
price_tier: medium
dimensions_mm:
- 64.77
- 22.86
usb:
  connector: usb-c
  bridge: ch340
power:
  battery_connector: true
  charging: true
extras:
- qwiic
- sd-card
- rgb-led
io:
  gpio_exposed: 21
  gpio_free: 15
  power_out:
    rail_v: [3.3]
    rail_ma_max: 700
notes:
- ESP32-WROOM-32E module; 16 MB flash
- Battery charging via onboard MCP73831 linear charge management controller (500mA max), JST connector for single-cell LiPo
- Onboard MAX17048 LiPo fuel gauge for battery-level monitoring
- Thing Plus form factor is pin-compatible with the Adafruit Feather footprint
- SparkFun's hardware overview states the module core is the ESP32-D0WDQ6 chip, an NRND ESP32 variant with no PSRAM per Espressif's ESP32 series ordering table
- 'io.gpio_exposed=21 QUOTED: vendor hardware overview states "...21 I/O pins
  broken out into a feather form factor layout on this board"'
- 'io.power_out QUOTED: vendor hardware overview states "The 3.3V XC6222 LDO
  regulator can source up to 700mA" (board''s 3.3V rail regulator)'
- 'io.gpio_free=15 DERIVED: the vendor''s own graphical datasheet shows 22 physical
  header GPIO pads (21,22,14,32,15,33,27,12,13 on the left header; 2,4,17,16,19,23,18,35,36,39,34,25,26
  on the right), but tags GPIO2 as dedicated to the onboard WS2812 RGB_BUILTIN
  LED and, in the "Other" features box, GPIO5 as the onboard microSD card''s
  CS line -- neither is a general-purpose header net, which nets out to the
  vendor''s own stated "21 I/O pins broken out" (22 pads - 1 RGB-dedicated =
  21; GPIO5 was never in the 22-pad header count, it is SD-internal only). Of
  esp32''s soc.reserved_pins, strapping 12/15 are exposed within that 21-set (0,
  2, and 5 are not, being absent/RGB/SD-dedicated as above); input_only
  34/35/36/39 are exposed (4 pins); usb_flash_tied 6/7/8 are not on the header.
  21 total - 2 strapping - 4 input-only = 15'
sources:
- field: '*'
  url: https://www.sparkfun.com/sparkfun-thing-plus-esp32-wroom-usb-c.html
  verified: '2026-08-22'
- field: usb.bridge
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-22'
- field: power
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-22'
- field: psram_mb
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-26'
- field: io.power_out
  url: https://docs.sparkfun.com/SparkFun_Thing_Plus_ESP32_WROOM_C/hardware_overview/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://cdn.sparkfun.com/assets/3/9/5/f/e/SparkFun_Thing_Plus_ESP32_WROOM_C_graphical_datasheet2.pdf
  verified: '2026-08-26'
---

# SparkFun Thing Plus - ESP32 WROOM (USB-C)

Feather-footprint-compatible ESP32-WROOM-32E board with USB-C, a microSD slot, Qwiic connector, and onboard LiPo charging with a fuel gauge. This is the current USB-C revision of SparkFun's Thing Plus ESP32 line; the earlier "ESP32 Thing Plus C" SKU (WRL-20168's predecessor) was retired in favor of this listing and is not tracked as a separate board.
