---
id: m5stick-s3
type: board
brand: m5stack
name: M5StickS3
soc: esp32-s3
flash_mb: 8
psram_mb: 8
form_factor: m5-stick
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 1.14in 135x240 LCD
extras:
- imu
- mic
- speaker
notes:
- ESP32-S3-PICO-1-N8R8; 8 MB flash, 8 MB PSRAM
- BMI270 6-axis IMU, ES8311 audio codec (mic + speaker), IR TX/RX
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/StickS3
  verified: '2026-08-23'
---

# M5StickS3

ESP32-S3 stick form factor: 1.14in LCD, IMU, ES8311 mic/speaker, IR TX/RX, USB-C, built-in 250mAh battery.
