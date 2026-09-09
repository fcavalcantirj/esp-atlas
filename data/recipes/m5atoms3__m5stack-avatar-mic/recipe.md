---
id: m5atoms3__m5stack-avatar-mic
type: recipe
board: m5atoms3
firmware: m5stack-avatar-mic
status: unverified
chip_family: esp32-s3
flash:
  env: "m5atoms3"
notes: "m5stack-avatar-mic names this board as esp32-s3-devkitc-1 in its platformio.ini (env m5atoms3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/mongonta0716/m5stack-avatar-mic
  verified: '2026-09-09'
- field: flash.env
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L52
  verified: '2026-09-09'
- field: board
  url: https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L52
  verified: '2026-09-09'
---

# m5atoms3 x m5stack-avatar-mic

`m5stack-avatar-mic` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `m5atoms3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/mongonta0716/m5stack-avatar-mic/blob/main/platformio.ini#L52
