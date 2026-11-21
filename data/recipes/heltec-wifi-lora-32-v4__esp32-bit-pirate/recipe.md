---
id: heltec-wifi-lora-32-v4__esp32-bit-pirate
type: recipe
board: heltec-wifi-lora-32-v4
firmware: esp32-bit-pirate
status: unverified
chip_family: esp32-s3
flash:
  env: "heltec_wifi_lora_32_V4"
notes: "esp32-bit-pirate names this board as esp32-s3-devkitc1-n16r2 in its platformio.ini (env heltec_wifi_lora_32_V4); derived from the repo's own build files, not verified on hardware. Evidence check v4 UNCERTAIN — negation: '| **Heltec WiFi LoRa 32 V4** | ![Photo of the Heltec WiFi LoRa 32 V4](/images/heltec-lora-32-v4_s.png) | 15 GPIO (Header'."
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-11-21'
- field: flash.env
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1351
  verified: '2026-11-21'
- field: board
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1351
  verified: '2026-11-21'
---

# heltec-wifi-lora-32-v4 x esp32-bit-pirate

`esp32-bit-pirate` declares `esp32-s3-devkitc1-n16r2` in its platformio.ini; that name resolves to the catalogued board `heltec-wifi-lora-32-v4` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc1-n16r2` — https://github.com/geo-tp/ESP32-Bit-Pirate/blob/pioarduino/platformio.ini#L1351
