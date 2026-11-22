---
id: m5cardputer-adv__esp32marauder
type: recipe
board: m5cardputer-adv
firmware: esp32marauder
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "esp32marauder names this board as m5cardputer_adv in its release (asset esp32_marauder_v1_20_0_20261028_m5cardputer_adv.bin) (release v1.20.0); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-11-19'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.20.0
  verified: '2026-11-19'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-11-19'
- field: board
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
  verified: '2026-11-19'
---

# m5cardputer-adv x esp32marauder

`esp32marauder` declares `m5cardputer_adv` in its release; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5cardputer_adv` — https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.20.0/esp32_marauder_v1_20_0_20261028_m5cardputer_adv.bin
- rank 3 ci: `M5Cardputer ADV` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `M5Cardputer ADV` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
- rank 3 ci: `m5cardputer_adv` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
- rank 3 ci: `m5cardputer_adv` — https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/nightly_build.yml
