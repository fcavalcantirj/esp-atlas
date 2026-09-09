---
id: m5stick-cplus2__m5stick-nemo
type: recipe
board: m5stick-cplus2
firmware: m5stick-nemo
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "m5stick-nemo names this board as M5StickCPlus2 in its release (asset M5Nemo-v3.2.2-M5StickCPlus2.bin) (release v3.2.2); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-09-09'
- field: board
  url: https://github.com/n0xa/m5stick-nemo/releases/tag/v3.2.2
  verified: '2026-09-09'
- field: board
  url: https://github.com/n0xa/m5stick-nemo/blob/main/.github/workflows/compile.yml
  verified: '2026-09-09'
- field: board
  url: https://github.com/n0xa/m5stick-nemo/blob/main/.github/workflows/dev_compile.yml
  verified: '2026-09-09'
---

# m5stick-cplus2 x m5stick-nemo

`m5stick-nemo` declares `M5StickCPlus2` in its release; that name resolves to the catalogued board `m5stick-cplus2` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `M5StickCPlus2` — https://github.com/n0xa/m5stick-nemo/releases/download/v3.2.2/M5Nemo-v3.2.2-M5StickCPlus2.bin
- rank 3 ci: `M5StickCPlus2` — https://github.com/n0xa/m5stick-nemo/blob/main/.github/workflows/compile.yml
- rank 3 ci: `M5StickCPlus2` — https://github.com/n0xa/m5stick-nemo/blob/main/.github/workflows/dev_compile.yml
