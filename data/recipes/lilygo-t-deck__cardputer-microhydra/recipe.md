---
id: lilygo-t-deck__cardputer-microhydra
type: recipe
board: lilygo-t-deck
firmware: cardputer-microhydra
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "cardputer-microhydra names this board as TDECK in its release (asset TDECK.bin) (release v2.5.1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/echo-lalia/MicroHydra
  verified: '2026-09-08'
- field: board
  url: https://github.com/echo-lalia/MicroHydra/releases/tag/v2.5.1
  verified: '2026-09-08'
---

# lilygo-t-deck x cardputer-microhydra

`cardputer-microhydra` declares `TDECK` in its release; that name resolves to the catalogued board `lilygo-t-deck` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `TDECK` — https://github.com/echo-lalia/MicroHydra/releases/download/v2.5.1/TDECK.bin
