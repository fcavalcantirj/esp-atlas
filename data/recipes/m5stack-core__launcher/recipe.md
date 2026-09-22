---
id: m5stack-core__launcher
type: recipe
board: m5stack-core
firmware: launcher
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "launcher names this board as m5stack-core in its release (asset Launcher-m5stack-core.bin) (release 2.9.1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-09-22'
- field: board
  url: https://github.com/bmorcelli/Launcher/releases/tag/2.9.1
  verified: '2026-09-22'
---

# m5stack-core x launcher

`launcher` declares `m5stack-core` in its release; that name resolves to the catalogued board `m5stack-core` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5stack-core` — https://github.com/bmorcelli/Launcher/releases/download/2.9.1/Launcher-m5stack-core.bin
