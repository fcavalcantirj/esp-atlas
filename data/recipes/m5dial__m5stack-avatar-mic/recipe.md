---
id: m5dial__m5stack-avatar-mic
type: recipe
board: m5dial
firmware: m5stack-avatar-mic
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-dial"
notes: "m5stack-avatar-mic names this board as esp32-s3-devkitc-1 in its platformio.ini (env m5stack-dial); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/mongonta0716/m5stack-avatar-mic
  verified: '2026-09-09'
- field: flash.env
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L73
  verified: '2026-09-09'
- field: board
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L73
  verified: '2026-09-09'
---

# m5dial x m5stack-avatar-mic

`m5stack-avatar-mic` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5dial` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L73
