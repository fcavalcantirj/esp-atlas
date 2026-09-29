---
id: um-pros3__esp32-bit-pirate
type: recipe
board: um-pros3
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "um_pros3"
notes: "esp32-bit-pirate names this board as um_pros3 in its platformio.ini (env um_pros3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-29'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1957
  verified: '2026-09-29'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1957
  verified: '2026-09-29'
---

# um-pros3 x esp32-bit-pirate

`esp32-bit-pirate` declares `um_pros3` in its platformio.ini; that name resolves to the catalogued board `um-pros3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `um_pros3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1957
