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
  stars: 201
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/D3CRYPT-1/Infiltra-Firmware
  verified: '2026-09-01'
---

# Infiltra

Infiltra is a Wi-Fi/BLE/sub-GHz pentesting firmware distributed via its own web flasher.
