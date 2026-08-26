---
id: lilygo-t-dongle-s3__usbarmyknife
type: recipe
board: lilygo-t-dongle-s3
firmware: usbarmyknife
status: unverified
chip_family: esp32-s3
firmware_version: v1.1.5
sources:
- field: '*'
  url: https://github.com/i-am-shodan/USBArmyKnife#supported-hardware
  verified: '2026-08-26'
- field: 'firmware_version'
  url: https://github.com/i-am-shodan/USBArmyKnife/releases/tag/v1.1.5
  verified: '2026-08-26'
---

# lilygo-t-dongle-s3 x usbarmyknife

The LilyGO T-Dongle S3 is USB Army Knife's explicitly "Recommended" hardware. Release
`v1.1.5` ships `LILYGO-T-Dongle-S3.Firmware.binaries.zip` — a multi-file bundle rather
than a single merged `.bin` — so no `flash.bin_url`/offset is recorded here.
