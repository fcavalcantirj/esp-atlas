---
id: lilygo-t-dongle-s3__ghostesp
type: recipe
board: lilygo-t-dongle-s3
firmware: ghostesp
status: unverified
chip_family: esp32-s3
notes: "ghostesp names this board as LilyGo T-Dongle-S3 in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/GhostESP-Revival/GhostESP
  verified: '2026-10-19'
- field: board
  url: https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
  verified: '2026-10-19'
---

# lilygo-t-dongle-s3 x ghostesp

`ghostesp` declares `LilyGo T-Dongle-S3` in its CI matrix; that name resolves to the catalogued board `lilygo-t-dongle-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `LilyGo T-Dongle-S3` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
- rank 3 ci: `TDongleS3` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
