---
id: lilygo-t-embed
type: board
brand: lilygo
name: T-Embed
soc: esp32-s3
psram_mb: 8
form_factor: t-embed
price_tier: medium
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 1.9in 170x320 ST7789 IPS TFT
extras:
- rotary-encoder
- microphone
- speaker
- rgb-led
- sd-card
notes:
- 1.25mm battery interface with charge/discharge protection circuit (not JST); battery not included
- Rotary encoder with integrated confirm button, 24 detents, 12 pulses/360°
- Dual microphones; 8ohm 1W speaker; 7x ring RGB LEDs
- TF (microSD) card holder; 2.54mm 8-pin GPIO header
- Wi-Fi 802.11 b/g/n, Bluetooth 5 + Bluetooth mesh
- Official schematic labels the chip ESP32-S3R8 (8 MB Octal-SPI in-package PSRAM per Espressif's ESP32-S3 series datasheet); the R8 chip variant has no in-package flash, and the external flash chip's exact capacity is not identified in available LilyGO documentation, so flash_mb is left unset
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-embed
  verified: '2026-08-22'
- field: psram_mb
  url: https://github.com/Xinyuan-LilyGO/T-Embed/blob/main/schematic/schematic.pdf
  verified: '2026-08-24'
---

# T-Embed

ESP32-S3 board with a 1.9in ST7789 IPS display, rotary encoder, dual mics, ring RGB LEDs, TF card slot, and USB-C with a 1.25mm battery charge/discharge circuit.
