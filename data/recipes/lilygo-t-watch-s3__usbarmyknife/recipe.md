---
id: lilygo-t-watch-s3__usbarmyknife
type: recipe
board: lilygo-t-watch-s3
firmware: usbarmyknife
status: unverified
chip_family: esp32-s3
flash:
  env: "LILYGO-T-Watch-S3"
notes: "usbarmyknife names this board as esp32-s3-devkitc-1 in its platformio.ini (env LILYGO-T-Watch-S3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/i-am-shodan/USBArmyKnife
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/i-am-shodan/USBArmyKnife/blob/master/platformio.ini#L408
  verified: '2026-09-10'
- field: board
  url: https://github.com/i-am-shodan/USBArmyKnife/blob/master/platformio.ini#L408
  verified: '2026-09-10'
---

# lilygo-t-watch-s3 x usbarmyknife

`usbarmyknife` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `lilygo-t-watch-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/i-am-shodan/USBArmyKnife/blob/master/platformio.ini#L408
