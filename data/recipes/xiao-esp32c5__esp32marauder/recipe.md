---
id: xiao-esp32c5__esp32marauder
type: recipe
board: xiao-esp32c5
firmware: esp32marauder
status: unverified
chip_family: esp32-c5
notes: "esp32marauder names this board as Seeed XIAO ESP32-C5 in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-10-13'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-10-13'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-10-13'
---

# xiao-esp32c5 x esp32marauder

`esp32marauder` declares `Seeed XIAO ESP32-C5` in its CI matrix; that name resolves to the catalogued board `xiao-esp32c5` (esp32-c5). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `Seeed XIAO ESP32-C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `Seeed XIAO ESP32-C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `XIAO_ESP32C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `XIAO_ESP32C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `XIAO_ESP32_C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `XIAO_ESP32_C5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `xiao_esp32c5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `xiao_esp32c5` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
