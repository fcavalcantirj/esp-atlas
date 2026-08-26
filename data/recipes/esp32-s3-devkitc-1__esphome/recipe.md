---
id: esp32-s3-devkitc-1__esphome
type: recipe
board: esp32-s3-devkitc-1
firmware: esphome
status: unverified
chip_family: esp32-s3
flash:
  method: web-flasher
notes: "ESPHome's `esp32:` component targets a standard Espressif devkit per chip variant by default; the Espressif ESP32-S3-DevKitC-1 is that reference board for `variant: esp32s3`, so any esphome YAML with that variant (or no board override) runs on it unmodified."
sources:
- field: '*'
  url: https://esphome.io/components/esp32.html
  verified: '2026-08-26'
---

# esp32-s3-devkitc-1 x esphome

ESPHome's `esp32:` component fills in a standard Espressif devkit board by default for a given chip `variant`; ESP32-S3-DevKitC-1 is that reference board for `esp32s3`, so it's a standard, unmodified target.
