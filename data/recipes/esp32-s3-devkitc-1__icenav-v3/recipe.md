---
id: esp32-s3-devkitc-1__icenav-v3
type: recipe
board: esp32-s3-devkitc-1
firmware: icenav-v3
status: build-target
chip_family: esp32-s3
claim:
  kind: pio-env
  repo:
    slug: jgauchia/IceNav-v3
    id: 474676130
  sha: 69e82f7c5d5e4d0fbcf164b394fa048978a06954
  env: MAKERF_ESP32S3
  board_id: esp32-s3-devkitc-1
  platformio_version: 6.2.0
  platform:
    spec: https://github.com/pioarduino/platform-espressif32/releases/download/55.03.312-1/platform-espressif32.zip
    package_digest: f147d4ec6d657f451742df497811ebe3377db583ffd2e321e34b3793ff6b20a2
    manifest_digest: 63b545b61c291bd897cb00a8ff5316e0ca0e0579add9f7d70d01415a11159415
  files:
  - path: platformio.ini
    blob: b4e07b656e4275b0a8befa904ad8e2457ddf32eb
  sections:
  - name: env:MAKERF_ESP32S3
    file: platformio.ini
    line: 131
  - name: esp32_common
    file: platformio.ini
    line: 61
  - name: common
    file: platformio.ini
    line: 15
sources:
- field: claim
  url: https://github.com/jgauchia/IceNav-v3/blob/69e82f7c5d5e4d0fbcf164b394fa048978a06954/platformio.ini#L131
  verified: '2026-11-25'
---

# esp32-s3-devkitc-1 x icenav-v3

At commit `69e82f7`, PlatformIO 6.2.0 resolves the environment `MAKERF_ESP32S3` of `jgauchia/IceNav-v3` to the board option `esp32-s3-devkitc-1`, which is this board's definition. Configuration only: not built or tested on hardware.
