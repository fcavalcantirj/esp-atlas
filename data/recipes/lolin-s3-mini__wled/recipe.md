---
id: lolin-s3-mini__wled
type: recipe
board: lolin-s3-mini
firmware: wled
status: known-good
chip_family: esp32-s3
flash:
  method: web-flasher
notes: "`board = lolin_s3_mini` in the esp32s3_4M_qspi environment (4 MB flash, 2 MB PSRAM build)."
sources:
- field: '*'
  url: https://raw.githubusercontent.com/wled/WLED/main/platformio.ini
  verified: '2026-08-24'
---

# lolin-s3-mini x wled

`board = lolin_s3_mini` in the esp32s3_4M_qspi environment (4 MB flash, 2 MB PSRAM build).
