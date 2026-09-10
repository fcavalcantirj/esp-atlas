---
id: lolin-c3-mini__openmqttgateway
type: recipe
board: lolin-c3-mini
firmware: openmqttgateway
status: unverified
chip_family: esp32-c3
flash:
  env: "esp32c3_lolin_mini"
notes: "openmqttgateway names this board as lolin_c3_mini in its platformio.ini (env esp32c3_lolin_mini); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L2045
  verified: '2026-09-10'
- field: board
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L2045
  verified: '2026-09-10'
---

# lolin-c3-mini x openmqttgateway

`openmqttgateway` declares `lolin_c3_mini` in its platformio.ini; that name resolves to the catalogued board `lolin-c3-mini` (esp32-c3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `lolin_c3_mini` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L2045
- rank 2 platformio: `lolin_c3_mini` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L2045
