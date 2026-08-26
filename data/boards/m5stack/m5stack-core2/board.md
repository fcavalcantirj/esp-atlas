---
id: m5stack-core2
type: board
brand: m5stack
name: Core2
soc: esp32
flash_mb: 16
psram_mb: 8
form_factor: m5-core
price_tier: medium
dimensions_mm:
- 54.0
- 54.0
- 16.5
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 2.0in 320x240 ILI9342C capacitive touch
extras:
- sd-card
- imu
- mic
- speaker
- rtc
- touch
io:
  gpio_free: 5
notes:
- 16 MB flash, 8 MB Quad PSRAM
- ESP32-D0WDQ6-V3; MPU6886 6-axis IMU, SPM1423 PDM mic, NS4168 speaker amp, BM8563
  RTC, AXP192 PMIC, 500mAh@3.7V battery, vibration motor, microSD slot
- 'io.gpio_free=5 DERIVED, not quoted (SPEC-io-power.md §5.3). Vendor page''s port
  description table states the three HY2.0-4P Grove ports: "PORT-A (Red) G32/33
  I2C", "PORT-B (Black) G26/36 DAC/ADC", "PORT-C (Blue) G13/14 UART" -- 6 pads
  total (32, 33, 26, 36, 13, 14), none shared with the LCD/SD/touch/mic/USB-serial
  pins the same page lists elsewhere. Subtracting esp32''s soc.reserved_pins that
  are exposed on those 6 -- G36 is input_only -- leaves 6 - 1 = 5. The 40-pin M-Bus
  header is excluded from this count: it re-exposes the same SoC pins already
  wired to onboard LCD/SD/touch/mic, so those pads are not free for independent
  use. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/core2
  verified: '2026-08-22'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/core2
  verified: '2026-08-26'
---

# Core2

54x54mm ESP32 core unit: 2.0in capacitive-touch IPS display, IMU, mic, speaker, vibration motor, microSD, USB-C, built-in 500mAh battery.
