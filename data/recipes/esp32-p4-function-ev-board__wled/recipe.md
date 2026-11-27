---
id: esp32-p4-function-ev-board__wled
type: recipe
board: esp32-p4-function-ev-board
firmware: wled
status: build-target
chip_family: esp32-p4
claim:
  kind: pio-env
  repo:
    slug: wled/WLED
    id: 76990209
  sha: 5e852a84e612b9a230c6d081b77f66d990783afc
  env: esp32p4_16MB
  board_id: esp32-p4-evboard
  platformio_version: 6.2.0
  platform:
    spec: https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip
    package_digest: ffce4a512581abd417c42edf2695a3b49e8b1447849847d3f62d0db695da9efc
    manifest_digest: 3ea208ff313739a724e032cdccc0a9be44ec760e19f301b3fa319079f9ca6575
  files:
  - path: platformio.ini
    blob: 3bf227bf97a50b79f50bf8e8a147036b3be86e8b
  sections:
  - name: env:esp32p4_16MB
    file: platformio.ini
    line: 596
  - name: env
    file: platformio.ini
    line: 132
  - name: esp32p4
    file: platformio.ini
    line: 478
  - name: esp32
    file: platformio.ini
    line: 273
  - name: common
    file: platformio.ini
    line: 55
  - name: scripts_defaults
    file: platformio.ini
    line: 116
  - name: esp32_idf_V5
    file: platformio.ini
    line: 324
  - name: esp32_all_variants
    file: platformio.ini
    line: 262
sources:
- field: claim
  url: https://github.com/wled/WLED/blob/5e852a84e612b9a230c6d081b77f66d990783afc/platformio.ini#L596
  verified: '2026-11-26'
---

# esp32-p4-function-ev-board x wled

At commit `5e852a8`, PlatformIO 6.2.0 resolves the environment `esp32p4_16MB` of `wled/WLED` to the board option `esp32-p4-evboard`, which is this board's definition. Configuration only: not built or tested on hardware.
