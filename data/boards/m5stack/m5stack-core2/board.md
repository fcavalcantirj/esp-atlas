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
notes:
- 16 MB flash, 8 MB Quad PSRAM
- ESP32-D0WDQ6-V3; MPU6886 6-axis IMU, SPM1423 PDM mic, NS4168 speaker amp, BM8563
  RTC, AXP192 PMIC, 500mAh@3.7V battery, vibration motor, microSD slot
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/core2
  verified: '2026-08-22'
---

# Core2

54x54mm ESP32 core unit: 2.0in capacitive-touch IPS display, IMU, mic, speaker, vibration motor, microSD, USB-C, built-in 500mAh battery.
