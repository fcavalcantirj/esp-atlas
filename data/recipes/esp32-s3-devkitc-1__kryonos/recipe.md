---
id: esp32-s3-devkitc-1__kryonos
type: recipe
board: esp32-s3-devkitc-1
firmware: kryonos
status: unverified
chip_family: esp32-s3
flash:
  env: "esp32-s3-devkitc-1-n16r8"
notes: "kryonos names this board as esp32-s3-devkitc-1 in its platformio.ini (env esp32-s3-devkitc-1-n16r8); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Haris16-code/KryonOS
  verified: '2026-11-12'
- field: flash.env
  url: https://github.com/Haris16-code/KryonOS/blob/main/platformio.ini#L22
  verified: '2026-11-12'
- field: board
  url: https://github.com/Haris16-code/KryonOS/blob/main/platformio.ini#L22
  verified: '2026-11-12'
- field: board
  url: https://github.com/Haris16-code/KryonOS/blob/main/.github/workflows/release.yml
  verified: '2026-11-12'
---

# esp32-s3-devkitc-1 x kryonos

`kryonos` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `esp32-s3-devkitc-1` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/Haris16-code/KryonOS/blob/main/platformio.ini#L22
- rank 3 ci: `esp32-s3-devkitc-1-n16r8` — https://github.com/Haris16-code/KryonOS/blob/main/.github/workflows/release.yml
