---
id: lilygo-t-beam__openmqttgateway
type: recipe
board: lilygo-t-beam
firmware: openmqttgateway
status: unverified
chip_family: esp32
flash:
  env: "ttgo-t-beam"
notes: "openmqttgateway names this board as ttgo-t-beam in its platformio.ini (env ttgo-t-beam); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1439
  verified: '2026-09-10'
- field: board
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1439
  verified: '2026-09-10'
---

# lilygo-t-beam x openmqttgateway

`openmqttgateway` declares `ttgo-t-beam` in its platformio.ini; that name resolves to the catalogued board `lilygo-t-beam` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `ttgo-t-beam` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1439
