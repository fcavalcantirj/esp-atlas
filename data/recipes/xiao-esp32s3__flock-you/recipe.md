---
id: xiao-esp32s3__flock-you
type: recipe
board: xiao-esp32s3
firmware: flock-you
status: unverified
chip_family: esp32-s3
flash:
  env: "xiao_esp32s3"
notes: "flock-you names this board as seeed_xiao_esp32s3 in its platformio.ini (env xiao_esp32s3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/colonelpanichacks/flock-you
  verified: '2026-09-08'
- field: flash.env
  url: https://github.com/colonelpanichacks/flock-you/blob/main/platformio.ini#L6
  verified: '2026-09-08'
- field: board
  url: https://github.com/colonelpanichacks/flock-you/blob/main/platformio.ini#L6
  verified: '2026-09-08'
---

# xiao-esp32s3 x flock-you

`flock-you` declares `seeed_xiao_esp32s3` in its platformio.ini; that name resolves to the catalogued board `xiao-esp32s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `seeed_xiao_esp32s3` — https://github.com/colonelpanichacks/flock-you/blob/main/platformio.ini#L6
