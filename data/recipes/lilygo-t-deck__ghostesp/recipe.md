---
id: lilygo-t-deck__ghostesp
type: recipe
board: lilygo-t-deck
firmware: ghostesp
status: unverified
chip_family: esp32-s3
notes: "ghostesp names this board as T-Deck in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/GhostESP-Revival/GhostESP
  verified: '2026-10-19'
- field: board
  url: https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
  verified: '2026-10-19'
---

# lilygo-t-deck x ghostesp

`ghostesp` declares `T-Deck` in its CI matrix; that name resolves to the catalogued board `lilygo-t-deck` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `T-Deck` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
