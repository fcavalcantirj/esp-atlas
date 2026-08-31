---
id: esp32-c5-devkitc-1__esp32marauder
type: recipe
board: esp32-c5-devkitc-1
firmware: esp32marauder
status: known-good
chip_family: esp32-c5
firmware_version: v1.15.1
flash:
  method: release-bin
  bin_url: https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.15.1/esp32_marauder_v1_15_1_20260824_esp32c5devkitc1.bin
  offset: '0x0'
notes: "ESP32 Marauder has a dedicated wiki page for the ESP32-C5-DevKitC-1 and ships a board-specific `...esp32c5devkitc1.bin` in its v1.15.1 release. The asset is a ~1.8 MB merged image (bootloader magic 0xE9 at byte 0), flashed at 0x0 like Marauder's other single-file board images."
sources:
- field: 'flash.bin_url'
  url: https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.15.1/esp32_marauder_v1_15_1_20260824_esp32c5devkitc1.bin
  verified: '2026-08-30'
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder/wiki/ESP32%E2%80%90C5%E2%80%90DevKitC%E2%80%901
  verified: '2026-08-30'
---

# esp32-c5-devkitc-1 x esp32marauder

ESP32 Marauder ships a board-specific build for the ESP32-C5-DevKitC-1
(`esp32_marauder_..._esp32c5devkitc1.bin`, v1.15.1) and documents it with a
dedicated wiki page. Merged image, flashed at 0x0 — flashes in-browser via
esp-atlas (release-bin → same-origin proxy).
