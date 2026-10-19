---
id: m5stack-cores3-se__ghostesp
type: recipe
board: m5stack-cores3-se
firmware: ghostesp
status: unverified
chip_family: esp32-s3
notes: "ghostesp names this board as M5Stack CoreS3-SE in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/GhostESP-Revival/GhostESP
  verified: '2026-10-19'
- field: board
  url: https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
  verified: '2026-10-19'
---

# m5stack-cores3-se x ghostesp

`ghostesp` declares `M5Stack CoreS3-SE` in its CI matrix; that name resolves to the catalogued board `m5stack-cores3-se` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `M5Stack CoreS3-SE` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
