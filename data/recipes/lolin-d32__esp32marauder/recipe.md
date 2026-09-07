---
id: lolin-d32__esp32marauder
type: recipe
board: lolin-d32
firmware: esp32marauder
status: unverified
chip_family: esp32
notes: "esp32marauder names this board as d32 in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-07'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-09-07'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-09-07'
---

# lolin-d32 x esp32marauder

`esp32marauder` declares `d32` in its CI matrix; that name resolves to the catalogued board `lolin-d32` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `d32` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `d32` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
