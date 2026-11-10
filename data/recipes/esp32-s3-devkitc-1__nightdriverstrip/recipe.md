---
id: esp32-s3-devkitc-1__nightdriverstrip
type: recipe
board: esp32-s3-devkitc-1
firmware: nightdriverstrip
status: unverified
chip_family: esp32-s3
flash:
  env: "mesmerizer_devkit_s3"
notes: "nightdriverstrip names this board as esp32-s3-devkitc-1 in its platformio.ini (env mesmerizer_devkit_s3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip
  verified: '2026-11-06'
- field: flash.env
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L1262
  verified: '2026-11-06'
- field: board
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L1262
  verified: '2026-11-06'
---

# esp32-s3-devkitc-1 x nightdriverstrip

`nightdriverstrip` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `esp32-s3-devkitc-1` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L1262
