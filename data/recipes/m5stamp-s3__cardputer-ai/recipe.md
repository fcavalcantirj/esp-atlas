---
id: m5stamp-s3__cardputer-ai
type: recipe
board: m5stamp-s3
firmware: cardputer-ai
status: build-target
chip_family: esp32-s3
claim:
  kind: pio-env
  repo:
    slug: therezor/cardputer-ai
    id: 1267077321
  sha: 78c5128672b750977619dc0a6c3b8baed91168ed
  env: cardputer
  board_id: m5stack-stamps3
  platformio_version: 6.2.0
  platform:
    spec: https://github.com/pioarduino/platform-espressif32/releases/download/55.03.39/platform-espressif32.zip
    package_digest: ad772f547ff6b396c307ebf989864ebf2b4b2347a3e87e2a042127de84abf8e0
    manifest_digest: a9294787f4312fef1219992ec933a963b6591549398d705a03653aac8c8b5fb2
  files:
  - path: platformio.ini
    blob: ceb24b5b953d61078bcfe5919ff177437928a617
  sections:
  - name: env:cardputer
    file: platformio.ini
    line: 18
sources:
- field: claim
  url: https://github.com/therezor/cardputer-ai/blob/78c5128672b750977619dc0a6c3b8baed91168ed/platformio.ini#L18
  verified: '2026-11-24'
---

# m5stamp-s3 x cardputer-ai

At commit `78c5128`, PlatformIO 6.2.0 resolves the environment `cardputer` of `therezor/cardputer-ai` to the board option `m5stack-stamps3`, which is this board's definition. Configuration only: not built or tested on hardware.
