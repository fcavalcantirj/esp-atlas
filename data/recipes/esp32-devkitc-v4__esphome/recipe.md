---
id: esp32-devkitc-v4__esphome
type: recipe
board: esp32-devkitc-v4
firmware: esphome
status: unverified
chip_family: esp32
flash:
  method: web-flasher
notes: "ESPHome's `esp32:` component targets a standard Espressif devkit per chip variant by default; the Espressif ESP32-DevKitC-V4 is that reference board for plain esp32, so any esphome YAML with `variant: esp32` (or no board override) runs on it unmodified."
sources:
- field: '*'
  url: https://esphome.io/components/esp32.html
  verified: '2026-08-26'
---

# esp32-devkitc-v4 x esphome

ESPHome's `esp32:` component fills in a standard Espressif devkit board by default for a given chip `variant`; ESP32-DevKitC-V4 is that reference board for plain ESP32, so it's a standard, unmodified target.
