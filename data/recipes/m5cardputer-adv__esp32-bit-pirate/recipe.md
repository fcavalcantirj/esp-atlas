---
id: m5cardputer-adv__esp32-bit-pirate
type: recipe
board: m5cardputer-adv
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer-adv"
notes: "esp32-bit-pirate names this board as m5stack-stamps3 in its platformio.ini (env cardputer-adv); derived from the repo's own build files, not verified on hardware. Evidence check v4 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-11-21'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L282
  verified: '2026-11-21'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L282
  verified: '2026-11-21'
---

# m5cardputer-adv x esp32-bit-pirate

`esp32-bit-pirate` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L282
