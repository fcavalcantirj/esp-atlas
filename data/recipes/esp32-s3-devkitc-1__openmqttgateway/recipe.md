---
id: esp32-s3-devkitc-1__openmqttgateway
type: recipe
board: esp32-s3-devkitc-1
firmware: openmqttgateway
status: unverified
chip_family: esp32-s3
flash:
  env: "esp32s3-dev-c1-ble"
notes: "openmqttgateway names this board as esp32-s3-devkitc-1 in its platformio.ini (env esp32s3-dev-c1-ble); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1903
  verified: '2026-09-10'
- field: board
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1903
  verified: '2026-09-10'
---

# esp32-s3-devkitc-1 x openmqttgateway

`openmqttgateway` declares `esp32-s3-devkitc-1` in its platformio.ini; that name resolves to the catalogued board `esp32-s3-devkitc-1` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `esp32-s3-devkitc-1` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1903
