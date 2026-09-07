---
id: m5nanoc6__esp32marauder
type: recipe
board: m5nanoc6
firmware: esp32marauder
status: unverified
chip_family: esp32-c6
flash:
  method: release-bin
notes: "esp32marauder names this board as m5nanoc6 in its release (asset esp32_marauder_v1_15_1_20260824_m5nanoc6.bin) (release v1.15.1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-07'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1
  verified: '2026-09-07'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-09-07'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-09-07'
---

# m5nanoc6 x esp32marauder

`esp32marauder` declares `m5nanoc6` in its release; that name resolves to the catalogued board `m5nanoc6` (esp32-c6). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5nanoc6` — https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.15.1/esp32_marauder_v1_15_1_20260824_m5nanoc6.bin
- rank 3 ci: `M5NanoC6` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `M5NanoC6` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `m5nanoc6` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `m5nanoc6` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
