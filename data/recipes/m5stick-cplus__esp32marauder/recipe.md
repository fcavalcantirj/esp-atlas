---
id: m5stick-cplus__esp32marauder
type: recipe
board: m5stick-cplus
firmware: esp32marauder
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "esp32marauder names this board as m5stickc_plus in its release (asset esp32_marauder_v1_17_0_20260916_m5stickc_plus.bin) (release v1.17.0); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-22'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.17.0
  verified: '2026-09-22'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-09-22'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-09-22'
---

# m5stick-cplus x esp32marauder

`esp32marauder` declares `m5stickc_plus` in its release; that name resolves to the catalogued board `m5stick-cplus` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5stickc_plus` — https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.17.0/esp32_marauder_v1_17_0_20260916_m5stickc_plus.bin
- rank 3 ci: `M5StickCPlus` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `M5StickCPlus` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `m5stickc_plus` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `m5stickc_plus` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
