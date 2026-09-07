---
id: waveshare-esp32-s3-touch-lcd-349
type: board
brand: waveshare
name: ESP32-S3-Touch-LCD-3.49
aka:
- "waveshare_touch_lcd_349"
soc: esp32-s3
flash_mb: 16
psram_mb: 8
display: 3.49in 172x640 IPS AXS15231B (capacitive touch)
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- sd-card
- imu
- mic
notes:
- 'Wiki: "Equipped with ESP32-S3R8 high-performance Xtensa 32-bit LX7 dual-core processor, up to 240MHz"; "stacked with 8MB PSRAM and external 16MB Flash" (bare chip with in-package PSRAM -> soc)'
- 'Display: "3.49inch high-definition capacitive touch IPS screen with a resolution of 172x640, 16.7M colors"; Driver IC "AXS15231B"; touch interface I2C'
- 'Onboard "QMI8658 6-axis IMU", "PCF85063 RTC", dual digital microphone array, audio codec; "3.7V MX1.25 lithium battery recharge/discharge header"; "TF card slot"; "22PIN 2.54mm pitch through-hole pads"; "Type-C port for program flashing and log printing"'
- 'aka "waveshare_touch_lcd_349" is the device token draftling uses for its release binaries'
sources:
- field: '*'
  url: https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.49
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
---

# Waveshare ESP32-S3-Touch-LCD-3.49

A 3.49-inch 172x640 touch IPS board on an ESP32-S3R8 (16 MB flash, 8 MB PSRAM) with IMU, RTC, microphones, a battery header and a TF-card slot.
