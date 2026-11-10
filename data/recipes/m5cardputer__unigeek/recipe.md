---
id: m5cardputer__unigeek
type: recipe
board: m5cardputer
firmware: unigeek
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "unigeek names this board as m5_cardputer in its release (asset unigeek-m5_cardputer.bin) (release 1.9.0); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/lshaf/unigeek
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/releases/tag/1.9.0
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cardputer/config.ini#L2
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
  verified: '2026-11-10'
---

# m5cardputer x unigeek

`unigeek` declares `m5_cardputer` in its release; that name resolves to the catalogued board `m5cardputer` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5_cardputer` — https://github.com/lshaf/unigeek/releases/download/1.9.0/unigeek-m5_cardputer.bin
- rank 2 platformio: `m5_cardputer` — https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cardputer/config.ini#L2
- rank 3 ci: `m5_cardputer` — https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
