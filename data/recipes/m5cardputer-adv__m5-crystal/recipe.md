---
id: m5cardputer-adv__m5-crystal
type: recipe
board: m5cardputer-adv
firmware: m5-crystal
status: unverified
chip_family: esp32-s3
flash:
  env: "cardputer-adv"
notes: "m5-crystal names this board as esp32-s3-devkitc-1 in its platformio.ini (env cardputer-adv); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-11-18'
- field: flash.env
  url: https://github.com/Dlazder/m5_crystal_firmware/blob/main/platformio.ini#L59
  verified: '2026-11-18'
- field: board
  url: https://github.com/Dlazder/m5_crystal_firmware/blob/main/platformio.ini#L59
  verified: '2026-11-18'
- field: board
  url: https://github.com/Dlazder/m5_crystal_firmware/blob/main/.github/workflows/build_pio.yml
  verified: '2026-11-18'
---

# m5cardputer-adv x m5-crystal

`m5-crystal` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/Dlazder/m5_crystal_firmware/blob/main/platformio.ini#L59
- rank 3 ci: `cardputer-adv` — https://github.com/Dlazder/m5_crystal_firmware/blob/main/.github/workflows/build_pio.yml
