---
id: lilygo-t-deck__kryonos
type: recipe
board: lilygo-t-deck
firmware: kryonos
status: unverified
chip_family: esp32-s3
flash:
  env: "lilygo-t-deck"
notes: "kryonos names this board as esp32-s3-devkitc-1 in its platformio.ini (env lilygo-t-deck); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Haris16-code/KryonOS
  verified: '2026-11-12'
- field: flash.env
  url: https://github.com/Haris16-code/KryonOS/blob/main/src/Hal/Boards/board_configs/t_deck.ini#L10
  verified: '2026-11-12'
- field: board
  url: https://github.com/Haris16-code/KryonOS/blob/main/src/Hal/Boards/board_configs/t_deck.ini#L10
  verified: '2026-11-12'
- field: board
  url: https://github.com/Haris16-code/KryonOS/blob/main/.github/workflows/release.yml
  verified: '2026-11-12'
---

# lilygo-t-deck x kryonos

`kryonos` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `lilygo-t-deck` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/Haris16-code/KryonOS/blob/main/src/Hal/Boards/board_configs/t_deck.ini#L10
- rank 3 ci: `lilygo-t-deck` — https://github.com/Haris16-code/KryonOS/blob/main/.github/workflows/release.yml
