---
id: lilygo-t-embed__flipper-zero-esp32-adv
type: recipe
board: lilygo-t-embed
firmware: flipper-zero-esp32-adv
status: unverified
chip_family: esp32-s3
notes: "flipper-zero-esp32-adv names this board as t_embed in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/Sor3nt/Flipper-Zero-ESP32-Port
  verified: '2026-09-08'
- field: board
  url: https://github.com/Sor3nt/Flipper-Zero-ESP32-Port/blob/main/.github/workflows/build.yml
  verified: '2026-09-08'
---

# lilygo-t-embed x flipper-zero-esp32-adv

`flipper-zero-esp32-adv` declares `t_embed` in its CI matrix; that name resolves to the catalogued board `lilygo-t-embed` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `t_embed` — https://github.com/Sor3nt/Flipper-Zero-ESP32-Port/blob/main/.github/workflows/build.yml
