---
id: m5stack-papers3__launcher
type: recipe
board: m5stack-papers3
firmware: launcher
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "launcher names this board as m5stack-paper-s3 in its release (asset Launcher-m5stack-paper-s3.bin) (release 2.9.1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-09-10'
- field: board
  url: https://github.com/bmorcelli/Launcher/releases/tag/2.9.1
  verified: '2026-09-10'
---

# m5stack-papers3 x launcher

`launcher` declares `m5stack-paper-s3` in its release; that name resolves to the catalogued board `m5stack-papers3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5stack-paper-s3` — https://github.com/bmorcelli/Launcher/releases/download/2.9.1/Launcher-m5stack-paper-s3.bin
