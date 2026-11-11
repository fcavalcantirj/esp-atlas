---
id: m5stack-cores3__unigeek
type: recipe
board: m5stack-cores3
firmware: unigeek
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "unigeek names this board as m5_cores3 in its release (asset unigeek-m5_cores3.bin) (release 1.9.0); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/lshaf/unigeek
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/releases/tag/1.9.0
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cores3/config.ini#L2
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cores3_unified/config.ini#L2
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
  verified: '2026-11-10'
---

# m5stack-cores3 x unigeek

`unigeek` declares `m5_cores3` in its release; that name resolves to the catalogued board `m5stack-cores3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5_cores3` — https://github.com/lshaf/unigeek/releases/download/1.9.0/unigeek-m5_cores3.bin
- rank 2 platformio: `m5_cores3` — https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cores3/config.ini#L2
- rank 2 platformio: `m5_cores3` — https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cores3_unified/config.ini#L2
- rank 3 ci: `m5_cores3` — https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
