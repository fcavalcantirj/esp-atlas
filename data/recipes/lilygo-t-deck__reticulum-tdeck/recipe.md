---
id: lilygo-t-deck__reticulum-tdeck
type: recipe
board: lilygo-t-deck
firmware: reticulum-tdeck
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the README's Hardware section names 'LilyGO T-Deck v1 (ESP32-S3)' with an SX1262 LoRa radio, and board_id.py ships BOARD = 'tdeck_v1' (the T-Deck Pro gets its own tdeck_pro_firmware.bin). Flash tdeck_firmware.bin at 0x0 or install it from M5Launcher. Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/varna9000/reticulum-tdeck/blob/dd6afceeffd5e86ec3220d7e120b2e2edd1ccb6d/README.md
  verified: '2026-11-14'
- field: board
  url: https://github.com/varna9000/reticulum-tdeck/blob/dd6afceeffd5e86ec3220d7e120b2e2edd1ccb6d/board_id.py
  verified: '2026-11-14'
---

T-Deck LXMF Messenger on the LilyGO T-Deck (ESP32-S3). `unverified`.

The project names the original T-Deck (v1) as its board and ships a dedicated full image for it.
That is source evidence of intended support; it has not been tested on hardware for this atlas.
