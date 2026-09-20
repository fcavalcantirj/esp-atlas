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
  verified: '2026-09-20'
summary: "RuView is a Wi\u2011Fi sensing platform that leverages Channel State Information\
  \ from low\u2011cost ESP32 sensors to detect presence, breathing, heart rate, activity\
  \ and camera\u2011free 17\u2011keypoint pose through walls, and exposes the data\
  \ as Home Assistant, Apple Home, Google Home and Alexa entities via MQTT/Matter.\
  \ It runs entirely on edge hardware (ESP32 mesh with optional Cognitum Seed) with\
  \ no cameras, wearables or cloud required."
readme_lang: en
readme_sha: bf998c8e4bd4184c1f412e21fecdcb6c2d96df33363c517d7a98e8e48aa33bd6
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
