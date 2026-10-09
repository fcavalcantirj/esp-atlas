---
id: m5stamp-s3__bytebed
type: recipe
board: m5stamp-s3
firmware: bytebed
status: unverified
chip_family: esp32-s3
flash:
  env: "m5stack-stamps3"
notes: "bytebed names this board as m5stack-stamps3 in its platformio.ini (env m5stack-stamps3); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/amiika/bytebed
  verified: '2026-10-09'
- field: flash.env
  url: https://github.com/amiika/bytebed/blob/main/platformio.ini#L6
  verified: '2026-10-09'
- field: board
  url: https://github.com/amiika/bytebed/blob/main/platformio.ini#L6
  verified: '2026-10-09'
---

# m5stamp-s3 x bytebed

`bytebed` declares `m5stack-stamps3` in its platformio.ini; that name resolves to the catalogued board `m5stamp-s3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-stamps3` — https://github.com/amiika/bytebed/blob/main/platformio.ini#L6
