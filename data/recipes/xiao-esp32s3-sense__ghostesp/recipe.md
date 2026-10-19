---
id: xiao-esp32s3-sense__ghostesp
type: recipe
board: xiao-esp32s3-sense
firmware: ghostesp
status: unverified
chip_family: esp32-s3
notes: "ghostesp names this board as xiao_esp32s3_sense in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/GhostESP-Revival/GhostESP
  verified: '2026-10-19'
- field: board
  url: https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
  verified: '2026-10-19'
---

# xiao-esp32s3-sense x ghostesp

`ghostesp` declares `xiao_esp32s3_sense` in its CI matrix; that name resolves to the catalogued board `xiao-esp32s3-sense` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `xiao_esp32s3_sense` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
