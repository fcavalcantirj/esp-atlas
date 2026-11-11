---
id: m5stamp-s3__esp32-bit-pirate
type: recipe
board: m5stamp-s3
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-stamps3"
notes: "esp32-bit-pirate has a dedicated m5stack-stamps3 env in its platformio.ini (-DDEVICE_M5STAMPS3) and lists the M5 StampS3 in its README; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-11-11'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L678
  verified: '2026-11-11'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L679
  verified: '2026-11-11'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/README.md#L66
  verified: '2026-11-11'
---

# m5stamp-s3 x esp32-bit-pirate

`esp32-bit-pirate` builds for this board from its own `m5stack-stamps3` env and lists the M5 StampS3 in its README. Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L679
- README device table: M5 StampS3 — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/README.md#L66
