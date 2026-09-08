---
id: m5stamp-s3__esp32-bit-pirate
type: recipe
board: m5stamp-s3
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer"
notes: "esp32-bit-pirate names this board as m5stack-stamps3 in its platformio.ini (env cardputer); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L240
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L240
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L352
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L793
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L904
  verified: '2026-09-08'
---

# m5stamp-s3 x esp32-bit-pirate

`esp32-bit-pirate` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L240
- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L352
- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L793
- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L904
