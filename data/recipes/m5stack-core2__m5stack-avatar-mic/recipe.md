---
id: m5stack-core2__m5stack-avatar-mic
type: recipe
board: m5stack-core2
firmware: m5stack-avatar-mic
status: unverified
chip_family: esp32
flash:
  env: "m5stack-core2"
notes: "m5stack-avatar-mic names this board as m5stack-core2 in its platformio.ini (env m5stack-core2); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/mongonta0716/m5stack-avatar-mic
  verified: '2026-09-09'
- field: flash.env
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L30
  verified: '2026-09-09'
- field: board
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L30
  verified: '2026-09-09'
---

# m5stack-core2 x m5stack-avatar-mic

`m5stack-avatar-mic` declares `m5stack-core2` in its platformio.ini; that name resolves to the catalogued board `m5stack-core2` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-core2` — https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L30
