---
id: m5stack-core__bruce
type: recipe
board: m5stack-core
firmware: bruce
status: unverified
chip_family: esp32
flash:
  env: "m5stack-core4mb"
notes: "bruce names this board as m5stack-core in its platformio.ini (env m5stack-core4mb); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BruceDevices/firmware
  verified: '2026-09-22'
- field: flash.env
  url: https://github.com/BruceDevices/firmware/blob/main/boards/m5stack-core/m5stack-core.ini#L12
  verified: '2026-09-22'
- field: board
  url: https://github.com/BruceDevices/firmware/blob/main/boards/m5stack-core/m5stack-core.ini#L12
  verified: '2026-09-22'
---

# m5stack-core x bruce

`bruce` declares `m5stack-core` in its platformio.ini; that name resolves to the catalogued board `m5stack-core` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-core` — https://github.com/BruceDevices/firmware/blob/main/boards/m5stack-core/m5stack-core.ini#L12
- rank 2 platformio: `m5stack-core` — https://github.com/BruceDevices/firmware/blob/main/boards/m5stack-core/m5stack-core.ini#L12
