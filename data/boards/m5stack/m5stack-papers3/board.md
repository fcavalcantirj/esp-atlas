---
id: m5stack-papers3
type: board
brand: m5stack
name: PaperS3
aka:
- "m5stack_papers3"
soc: esp32-s3
flash_mb: 16
psram_mb: 8
display: 4.7in 960x540 e-ink EPD_ED047TC1 (16-level grayscale, touch)
power:
  battery_connector: true
  charging: true
dimensions_mm:
- 121.5
- 67.7
- 7.7
extras:
- sd-card
notes:
- 'Official page: "ESP32-S3R8 @ Xtensa 32-bit LX7 dual-core processor, clock frequency 240MHz", "16MB" flash, "8MB Octal" PSRAM (bare chip with in-package PSRAM, no WROOM module -> soc)'
- 'Display: "4.7 touch e-ink screen (full screen) @EPD_ED047TC1 Resolution: 960x540 pixels 16-level grayscale display"'
- 'Battery: "3.7V@1800mAh lithium battery" on a "HY1.25-2P" battery interface; charging "DC 5V@331.5mA"; ports: "HC1.25-4PLT (3v3 + GND + 2 x GPIO) peripheral interface", microSD; one physical button (power/reset/download)'
- USB connector type is not stated on the official page (omitted); the page lists USB OTG/CDC/MSC flashing (native ESP32-S3 USB)
- 'aka "m5stack_papers3" is the device token draftling uses for its release binaries'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/papers3
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
---

# M5Stack PaperS3

A 4.7-inch touch e-ink handheld around an ESP32-S3R8 (16 MB flash, 8 MB PSRAM) with a 1800 mAh battery, microSD slot and one HC1.25-4P port.
