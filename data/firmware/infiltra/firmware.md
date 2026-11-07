---
id: infiltra
type: firmware
name: Infiltra
url: https://github.com/D3CRYPT-1/Infiltra-Firmware
category: pentest
maintainer: D3CRYPT-1
license: GPL-2.0
socs:
- esp32
- esp32-s3
distribution:
- web-flasher
- releases
capabilities:
- wifi
- ble
- sub-ghz
requires:
- capability: wifi
  board_signal: radio-wifi
- capability: ble
  board_signal: radio-ble
- capability: sub-ghz
  why: sub-GHz tools need an on-board CC1101
  board_signal: null
not_required:
- capability: psram
popularity:
  stars: 207
  forks: 14
  as_of: '2026-11-07'
  github_repo_id: 917929512
  github_as_of: '2026-11-07T13:05:00Z'
sources:
- field: '*'
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-09-01'
- field: summary
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-09-20'
- field: popularity.forks
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-11-07'
- field: popularity.github_as_of
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-11-07'
- field: popularity.github_repo_id
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-11-07'
- field: popularity.stars
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-11-07'
summary: "Infiltra Firmware is an open\u2011source custom firmware for ESP\u2011based\
  \ devices (e.g., M5Stick, Cardputer, Flipper Zero, etc.) that equips hackers and\
  \ security enthusiasts with a comprehensive toolkit for wireless testing, including\
  \ Sub\u2011GHz, Wi\u2011Fi, BLE, RFID/NFC, IR, and NRF24L01+ signal capture, emulation,\
  \ jamming, and attack capabilities."
readme_lang: en
readme_sha: 854059063be82c40869ce9eff692608e48efcadccb1535408e166f86bacc3da4
---

# Infiltra

Infiltra is a Wi-Fi/BLE/sub-GHz pentesting firmware distributed via its own web flasher.
