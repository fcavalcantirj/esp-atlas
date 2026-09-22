---
id: m5stick-c__esp32marauder
type: recipe
board: m5stick-c
firmware: esp32marauder
status: unverified
chip_family: esp32
notes: "esp32marauder names this board as m5stick-c in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-22'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-09-22'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-09-22'
---

# m5stick-c x esp32marauder

`esp32marauder` declares `m5stick-c` in its CI matrix; that name resolves to the catalogued board `m5stick-c` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `m5stick-c` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `m5stick-c` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
