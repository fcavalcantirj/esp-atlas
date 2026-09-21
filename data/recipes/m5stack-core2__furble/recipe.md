---
id: m5stack-core2__furble
type: recipe
board: m5stack-core2
firmware: furble
status: unverified
chip_family: esp32
flash:
  env: "m5stack-core2"
notes: "furble names this board as m5stack-core2 in its platformio.ini (env m5stack-core2); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/gkoh/furble
  verified: '2026-09-21'
- field: flash.env
  url: https://github.com/gkoh/furble/blob/master/platformio.ini#L36
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/platformio.ini#L36
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/.github/workflows/main.yml
  verified: '2026-09-21'
- field: board
  url: https://github.com/gkoh/furble/blob/master/.github/workflows/release.yml
  verified: '2026-09-21'
---

# m5stack-core2 x furble

`furble` declares `m5stack-core2` in its platformio.ini; that name resolves to the catalogued board `m5stack-core2` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-core2` — https://github.com/gkoh/furble/blob/master/platformio.ini#L36
- rank 3 ci: `m5stack-core2` — https://github.com/gkoh/furble/blob/master/.github/workflows/main.yml
- rank 3 ci: `m5stack-core2` — https://github.com/gkoh/furble/blob/master/.github/workflows/release.yml
