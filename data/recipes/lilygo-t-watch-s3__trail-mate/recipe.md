---
id: lilygo-t-watch-s3__trail-mate
type: recipe
board: lilygo-t-watch-s3
firmware: trail-mate
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "trail-mate names this board as lilygo_twatch_s3 in its release (asset trail-mate-lilygo_twatch_s3-v1.0.1.bin) (release v1.0.1); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/vicliu624/trail-mate
  verified: '2026-11-08'
- field: board
  url: https://github.com/vicliu624/trail-mate/releases/tag/v1.0.1
  verified: '2026-11-08'
- field: board
  url: https://github.com/vicliu624/trail-mate/blob/main/variants/lilygo_twatch_s3/envs/lilygo_twatch_s3.ini#L3
  verified: '2026-11-08'
- field: board
  url: https://github.com/vicliu624/trail-mate/blob/main/variants/lilygo_twatch_s3/envs/lilygo_twatch_s3.ini#L48
  verified: '2026-11-08'
- field: board
  url: https://github.com/vicliu624/trail-mate/blob/main/.github/workflows/ci.yml
  verified: '2026-11-08'
---

# lilygo-t-watch-s3 x trail-mate

`trail-mate` declares `lilygo_twatch_s3` in its release; that name resolves to the catalogued board `lilygo-t-watch-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `lilygo_twatch_s3` — https://github.com/vicliu624/trail-mate/releases/download/v1.0.1/trail-mate-lilygo_twatch_s3-v1.0.1.bin
- rank 2 platformio: `lilygo-t-watch-s3` — https://github.com/vicliu624/trail-mate/blob/main/variants/lilygo_twatch_s3/envs/lilygo_twatch_s3.ini#L3
- rank 2 platformio: `lilygo-t-watch-s3` — https://github.com/vicliu624/trail-mate/blob/main/variants/lilygo_twatch_s3/envs/lilygo_twatch_s3.ini#L48
- rank 3 ci: `lilygo_twatch_s3` — https://github.com/vicliu624/trail-mate/blob/main/.github/workflows/ci.yml
