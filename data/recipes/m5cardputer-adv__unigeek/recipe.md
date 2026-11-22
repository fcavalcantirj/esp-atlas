---
id: m5cardputer-adv__unigeek
type: recipe
board: m5cardputer-adv
firmware: unigeek
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "unigeek names this board as m5_cardputer_adv in its release (asset unigeek-m5_cardputer_adv.bin) (release 1.9.0); derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/lshaf/unigeek
  verified: '2026-11-18'
- field: board
  url: https://github.com/lshaf/unigeek/releases/tag/1.9.0
  verified: '2026-11-18'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cardputer_adv/config.ini#L2
  verified: '2026-11-18'
- field: board
  url: https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
  verified: '2026-11-18'
---

# m5cardputer-adv x unigeek

`unigeek` declares `m5_cardputer_adv` in its release; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5_cardputer_adv` — https://github.com/lshaf/unigeek/releases/download/1.9.0/unigeek-m5_cardputer_adv.bin
- rank 2 platformio: `m5_cardputer_adv` — https://github.com/lshaf/unigeek/blob/main/firmware/boards/m5_cardputer_adv/config.ini#L2
- rank 3 ci: `m5_cardputer_adv` — https://github.com/lshaf/unigeek/blob/main/.github/workflows/release.yml
