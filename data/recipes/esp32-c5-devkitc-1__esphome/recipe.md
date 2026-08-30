---
id: esp32-c5-devkitc-1__esphome
type: recipe
board: esp32-c5-devkitc-1
firmware: esphome
status: unverified
chip_family: esp32-c5
flash:
  method: web-flasher
notes: "ESPHome's `esp32:` component targets a standard Espressif devkit per chip variant by default; the ESP32-C5-DevKitC-1 is that reference board for `variant: esp32c5`, so any esphome YAML with that variant (or no board override) runs on it unmodified. Mirrors the esp32-c6-devkitc-1 precedent; not independently hardware-verified."
sources:
- field: '*'
  url: https://esphome.io/components/esp32.html
  verified: '2026-08-30'
---

# esp32-c5-devkitc-1 x esphome

ESPHome's `esp32:` component fills in a standard Espressif devkit board by default
for a given chip `variant`; ESP32-C5-DevKitC-1 is that reference board for
`esp32c5`, so it's a standard, unmodified target.
