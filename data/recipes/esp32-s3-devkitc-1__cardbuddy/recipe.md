---
id: esp32-s3-devkitc-1__cardbuddy
type: recipe
board: esp32-s3-devkitc-1
firmware: cardbuddy
status: build-target
chip_family: esp32-s3
claim:
  kind: pio-env
  repo:
    slug: konsumer/cardbuddy
    id: 1460931781
  sha: 720c7e56f3a40606d60c2239e3b2e3522a1601a7
  env: cardputer
  board_id: esp32-s3-devkitc-1
  platformio_version: 6.2.0
  platform:
    spec: https://github.com/pioarduino/platform-espressif32/releases/download/55.03.312/platform-espressif32.zip
    package_digest: a87867b9c83cda963679da588cd2d02a73d4d5aea7cde099f7492495d3226f15
    manifest_digest: 63b545b61c291bd897cb00a8ff5316e0ca0e0579add9f7d70d01415a11159415
  files:
  - path: platformio.ini
    blob: d4ae895a6480a3e2c4341fa520f77de95439cfe6
  sections:
  - name: env:cardputer
    file: platformio.ini
    line: 9
sources:
- field: claim
  url: https://github.com/konsumer/cardbuddy/blob/720c7e56f3a40606d60c2239e3b2e3522a1601a7/platformio.ini#L9
  verified: '2026-11-24'
---

# esp32-s3-devkitc-1 x cardbuddy

At commit `720c7e5`, PlatformIO 6.2.0 resolves the environment `cardputer` of `konsumer/cardbuddy` to the board option `esp32-s3-devkitc-1`, which is this board's definition. Configuration only: not built or tested on hardware.
