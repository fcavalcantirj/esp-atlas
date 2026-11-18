---
id: m5cardputer__m5-crystal
type: recipe
board: m5cardputer
firmware: m5-crystal
status: unverified
chip_family: esp32-s3
notes: "m5-crystal names this board as Cardputer in its platformio.ini; derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer."
sources:
- field: '*'
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-11-18'
- field: board
  url: https://github.com/Dlazder/m5_crystal_firmware/blob/main/platformio.ini#L59
  verified: '2026-11-18'
---

# m5cardputer x m5-crystal

`m5-crystal` declares `Cardputer` in its platformio.ini; that name resolves to the catalogued board `m5cardputer` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `Cardputer` — https://github.com/Dlazder/m5_crystal_firmware/blob/main/platformio.ini#L59
