---
id: esp32-s3-devkitc-1__esp32-bit-pirate
type: recipe
board: esp32-s3-devkitc-1
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "s3-devkit"
notes: "esp32-bit-pirate names this board as esp32-s3-devkitc-1 in its platformio.ini (env s3-devkit); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L581
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L581
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L686
  verified: '2026-09-08'
---

# esp32-s3-devkitc-1 x esp32-bit-pirate

`esp32-bit-pirate` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `esp32-s3-devkitc-1` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L581
- rank 2 platformio: `esp32-s3-devkitc1-n16r8` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L686
