---
id: adafruit-matrixportal-s3__wled
type: recipe
board: adafruit-matrixportal-s3
firmware: wled
status: known-good
chip_family: esp32-s3
flash:
  method: web-flasher
notes: "Dedicated `[env:adafruit_matrixportal_esp32s3]` HUB75 environment, with a board-specific release build."
sources:
- field: '*'
  url: https://raw.githubusercontent.com/wled/WLED/main/platformio.ini
  verified: '2026-08-24'
---

# adafruit-matrixportal-s3 x wled

Dedicated `[env:adafruit_matrixportal_esp32s3]` HUB75 environment, with a board-specific release build.
