---
id: esp32-c5-devkitc-1__esphome
type: recipe
board: esp32-c5-devkitc-1
firmware: esphome
status: known-good
chip_family: esp32-c5
firmware_version: 2026.8.2
flash:
  method: web-flasher
notes: "ESPHome's `esp32:` component targets a standard Espressif devkit per chip variant by default; the ESP32-C5-DevKitC-1 is that reference board for `variant: esp32c5`, so any esphome YAML with that variant (or no board override) runs on it unmodified. Verified on real hardware 2026-09-01: ESPHome 2026.8.2 (`framework: esp-idf`, ESP-IDF 5.5.5) compiled for `variant: esp32c5`, flashed as the factory image at 0x0 with esptool 5.3.0 over the USB-to-UART port; boots and logs `ESP32 Chip: ESP32-C5 rev1.2`, and drives the onboard GPIO27 WS2812 through `esp32_rmt_led_strip`. Note: the same chip revision answers CHIP magic 0x30e1706f, which the in-browser flashers (esptool-js 0.6.1) do not recognise -- web.esphome.io could not detect it; the CLI + esptool path works."
sources:
- field: '*'
  url: https://esphome.io/components/esp32.html
  verified: '2026-08-30'
---

# esp32-c5-devkitc-1 x esphome

ESPHome's `esp32:` component fills in a standard Espressif devkit board by default
for a given chip `variant`; ESP32-C5-DevKitC-1 is that reference board for
`esp32c5`, so it's a standard, unmodified target.
