---
id: m5dial
type: board
brand: m5stack
name: Dial
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-dial
price_tier: medium
dimensions_mm:
- 51.0
- 51.0
- 32.3
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 1.28in 240x240 circular TFT GC9A01, FT3267 touch
extras:
- rtc
- rfid
- touch
- speaker
notes:
- ESP32-S3FN8; 8 MB flash. ESP32-S3FN8 ordering code has no PSRAM, per Espressif's ESP32-S3 series datasheet
- BM8563 RTC, WS1850S 13.56MHz RFID, rotary encoder (16 detents/64 pulses per rev),
  80dB buzzer, 1.25mm-2P battery connector with onboard charging circuit (battery
  sold separately), PORT.A/PORT.B GPIO expansion
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/M5Dial
  verified: '2026-08-22'
- field: psram_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-08-24'
---

# Dial

51x51mm ESP32-S3 rotary-knob unit: circular touch display, rotary encoder, RFID reader, RTC, USB-C, onboard charging circuit.
