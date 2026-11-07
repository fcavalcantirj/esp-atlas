---
id: lolin-d32-pro__nightdriverstrip
type: recipe
board: lolin-d32-pro
firmware: nightdriverstrip
status: unverified
chip_family: esp32
flash:
  env: "mesmerizer_lolin"
notes: "nightdriverstrip names this board as lolin_d32_pro in its platformio.ini (env mesmerizer_lolin); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip
  verified: '2026-11-07'
- field: flash.env
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L211
  verified: '2026-11-07'
- field: board
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L211
  verified: '2026-11-07'
---

# lolin-d32-pro x nightdriverstrip

`nightdriverstrip` declares `lolin_d32_pro` in its platformio.ini; that name resolves to the catalogued board `lolin-d32-pro` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `lolin_d32_pro` — https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/main/platformio.ini#L211
