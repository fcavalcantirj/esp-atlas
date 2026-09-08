---
id: heltec-wifi-lora-32-v3__esp32-bit-pirate
type: recipe
board: heltec-wifi-lora-32-v3
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "heltec_wifi_lora_32_V3"
notes: "esp32-bit-pirate names this board as heltec_wifi_lora_32_V3 in its platformio.ini (env heltec_wifi_lora_32_V3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1850
  verified: '2026-09-08'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1850
  verified: '2026-09-08'
---

# heltec-wifi-lora-32-v3 x esp32-bit-pirate

`esp32-bit-pirate` declares `heltec_wifi_lora_32_V3` in its platformio.ini; that name resolves to the catalogued board `heltec-wifi-lora-32-v3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `heltec_wifi_lora_32_V3` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1850
