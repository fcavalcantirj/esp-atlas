---
id: esp32-pico-kit__openmqttgateway
type: recipe
board: esp32-pico-kit
firmware: openmqttgateway
status: build-target
chip_family: esp32
claim:
  kind: pio-env
  repo:
    slug: 1technophile/OpenMQTTGateway
    id: 68460326
  sha: fb41b7ab9b4cbe13b08804d216ea8386661853b2
  env: esp32-m5atom-lite
  board_id: pico32
  platformio_version: 6.2.0
  platform:
    spec: https://github.com/pioarduino/platform-espressif32/releases/download/55.03.39/platform-espressif32.zip
    package_digest: ad772f547ff6b396c307ebf989864ebf2b4b2347a3e87e2a042127de84abf8e0
    manifest_digest: c76d54202495c336bc8c57ec7f67f80a242192a94344d138cb03a5cd60d44063
  files:
  - path: platformio.ini
    blob: a8138f26f4195c438d07cf0e4c0ffd92f8453bea
  - path: environments.ini
    blob: f2ea97319d575034aaf0986993974f4165c5ffb8
  sections:
  - name: env:esp32-m5atom-lite
    file: environments.ini
    line: 828
  - name: env
    file: platformio.ini
    line: 167
  - name: com
    file: platformio.ini
    line: 181
  - name: com-esp32
    file: platformio.ini
    line: 199
  - name: libraries
    file: platformio.ini
    line: 119
sources:
- field: claim
  url: https://github.com/1technophile/OpenMQTTGateway/blob/fb41b7ab9b4cbe13b08804d216ea8386661853b2/environments.ini#L828
  verified: '2026-11-25'
---

# esp32-pico-kit x openmqttgateway

At commit `fb41b7a`, PlatformIO 6.2.0 resolves the environment `esp32-m5atom-lite` of `1technophile/OpenMQTTGateway` to the board option `pico32`, which is this board's definition. Configuration only: not built or tested on hardware.
