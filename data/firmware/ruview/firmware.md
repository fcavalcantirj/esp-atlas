---
id: ruview
type: firmware
name: RuView
url: https://github.com/ruvnet/RuView
category: multi
maintainer: ruvnet
license: MIT
capabilities:
- wifi
popularity:
  stars: 94567
  forks: 12520
  as_of: '2026-09-20'
socs:
- esp32-s3
- esp32-c6
sources:
- field: '*'
  url: https://github.com/ruvnet/RuView
  verified: '2026-09-04'
- field: popularity
  url: https://github.com/ruvnet/RuView
  verified: '2026-09-04'
- field: socs
  url: https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32
  verified: '2026-09-04'
- field: socs
  url: https://github.com/ruvnet/RuView/blob/main/firmware/esp32-csi-node/sdkconfig.defaults.esp32c6
  verified: '2026-09-04'
- field: summary
  url: https://github.com/ruvnet/RuView
  verified: '2026-10-06'
summary: "RuView is a WiFi\u2011based sensing platform that captures Channel State\
  \ Information from low\u2011cost ESP32 nodes to detect presence, occupancy, breathing,\
  \ heart rate, activity, and camera\u2011free 17\u2011keypoint pose through walls,\
  \ and exposes this data to major smart\u2011home ecosystems via MQTT and Matter.\
  \ It runs entirely on edge hardware (ESP32 mesh with optional Cognitum Seed) and\
  \ includes a suite of modular AI\u2011driven analytics and automation tools."
readme_lang: en
readme_sha: 27add259c55ead3a56a0ba4492f3d33c3d93597f596fb3561dbcdaa8dd377983
---

RuView turns commodity WiFi signals into spatial sensing — presence detection,
motion, and vital-sign estimation — with no camera and nothing worn. The ESP32
side of the project is `firmware/esp32-csi-node`, an ESP-IDF v5.4 application
that captures WiFi Channel State Information and streams it to a RuView sensing
server.

It builds for two chips. `CONFIG_IDF_TARGET="esp32s3"` is the production target
(`sdkconfig.defaults`, `sdkconfig.defaults.4mb`) and `CONFIG_IDF_TARGET="esp32c6"`
is the research target (`sdkconfig.defaults.esp32c6`), which the project's README
describes as its Wi-Fi 6 / 802.15.4 / TWT path. The `v0.8.8-esp32` release ships
prebuilt bundles for both: `s3-8mb`, `s3-4mb` and `c6-4mb`.

Installing is a four-file job, not a single image. Each `…-flash-bundle.zip`
carries a bootloader, partition table, OTA metadata and application, written at
`bootloader=0x0`, `partition-table=0x8000`, `otadata=0xf000`, `app (ota_0)=0x20000`.
The bare `…-.bin` asset is the application alone; the project warns that writing
only `0x20000` is safe just for a node already provisioned and reporting
`running_partition: ota_0`. Never flash an S3 bundle onto a C6, or the reverse.
