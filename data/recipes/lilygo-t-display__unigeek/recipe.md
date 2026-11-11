---
id: lilygo-t-display__unigeek
type: recipe
board: lilygo-t-display
firmware: unigeek
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "unigeek names this board as t_display in its release (asset unigeek-t_display.bin) (release 1.9.0); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/lshaf/unigeek
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/releases/tag/1.9.0
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/firmware/boards/t_display/config.ini#L2
  verified: '2026-11-10'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
  verified: '2026-11-10'
---

# lilygo-t-display x unigeek

`unigeek` declares `t_display` in its release; that name resolves to the catalogued board `lilygo-t-display` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `t_display` — https://github.com/lshaf/unigeek/releases/download/1.9.0/unigeek-t_display.bin
- rank 2 platformio: `t_display` — https://github.com/lshaf/unigeek/blob/main/firmware/boards/t_display/config.ini#L2
- rank 3 ci: `t_display` — https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
