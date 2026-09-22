---
id: m5stack-fire__m5stack-avatar-mic
type: recipe
board: m5stack-fire
firmware: m5stack-avatar-mic
status: unverified
chip_family: esp32
flash:
  env: "m5stack-fire"
notes: "m5stack-avatar-mic names this board as m5stack-fire in its platformio.ini (env m5stack-fire); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/mongonta0716/m5stack-avatar-mic
  verified: '2026-09-22'
- field: flash.env
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L39
  verified: '2026-09-22'
- field: board
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L39
  verified: '2026-09-22'
---

# m5stack-fire x m5stack-avatar-mic

`m5stack-avatar-mic` declares `m5stack-fire` in its platformio.ini; that name resolves to the catalogued board `m5stack-fire` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-fire` — https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L39
