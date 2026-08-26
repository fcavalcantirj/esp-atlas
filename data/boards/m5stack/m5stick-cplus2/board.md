---
id: m5stick-cplus2
type: board
brand: m5stack
name: StickC-Plus2
soc: esp32
flash_mb: 8
psram_mb: 2
form_factor: m5-stick
price_tier: medium
dimensions_mm:
- 48.0
- 24.0
- 13.5
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 1.14in 135x240 TFT ST7789v2
extras:
- imu
- mic
- rtc
io:
  gpio_exposed: 6
  gpio_free: 4
notes:
- ESP32-PICO-V3-02; 8 MB flash, 2 MB Quad PSRAM
- MPU6886 3-axis accel + 3-axis gyro, SPM1423 mic, BM8563 RTC, passive buzzer, IR
  emitter, 200mAh@3.7V internal battery
- 'io.gpio_exposed=6 COUNTED: page states "External Pins: G0, G25/G26, G36, G32,
  G33" = {0,25,26,32,33,36}; the HY2.0-4P Grove port reuses the same G32/G33 pads
  ("Yellow: G32, White: G33"), no new pins added. Buttons (G35/G37/G39), display
  (G5/G12/G13/G14/G15/G27), mic DATA (G34), IR (G19), buzzer (G2), and power-hold
  (G4) are all internal, not in the External Pins list. io.gpio_free=4 DERIVED:
  subtracting esp32''s soc.reserved_pins that land in the exposed set -- G0 is
  strapping, G36 is input_only -- gives 6 - 2 = 4 (G25/G26/G32/G33 remain). No
  max Grove/rail output current stated on this page, so power_out is omitted.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/M5StickC%20PLUS2
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/M5StickC%20PLUS2
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/M5StickC%20PLUS2
  verified: '2026-08-26'
---

# StickC-Plus2

48x24mm ESP32-PICO stick form factor: 1.14in TFT, IMU, mic, buzzer, IR emitter, USB-C, built-in 200mAh battery.
