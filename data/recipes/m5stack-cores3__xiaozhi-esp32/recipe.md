---
id: m5stack-cores3__xiaozhi-esp32
type: recipe
board: m5stack-cores3
firmware: xiaozhi-esp32
status: unverified
chip_family: esp32-s3
firmware_version: v2.4.2
sources:
- field: '*'
  url: https://github.com/78/xiaozhi-esp32#readme
  verified: '2026-08-26'
- field: 'firmware_version'
  url: https://github.com/78/xiaozhi-esp32/releases/tag/v2.4.2
  verified: '2026-08-26'
---

# m5stack-cores3 x xiaozhi-esp32

M5Stack CoreS3 is listed among xiaozhi-esp32's explicitly supported boards; release
v2.4.2 ships a `v2.4.2_m5stack-core-s3.zip` build bundle (bootloader + partition table +
app, no single merged `.bin`) rather than a one-file image, so no `flash.bin_url`/offset
is recorded here — follow the per-board build/flash instructions in the release asset.
