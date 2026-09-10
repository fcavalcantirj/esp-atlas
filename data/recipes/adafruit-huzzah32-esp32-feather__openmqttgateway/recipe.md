---
id: adafruit-huzzah32-esp32-feather__openmqttgateway
type: recipe
board: adafruit-huzzah32-esp32-feather
firmware: openmqttgateway
status: unverified
chip_family: esp32
flash:
  env: "esp32feather-ble"
notes: "openmqttgateway names this board as featheresp32 in its platformio.ini (env esp32feather-ble); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L508
  verified: '2026-09-10'
- field: board
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L508
  verified: '2026-09-10'
---

# adafruit-huzzah32-esp32-feather x openmqttgateway

`openmqttgateway` declares `featheresp32` in its platformio.ini; that name resolves to the catalogued board `adafruit-huzzah32-esp32-feather` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `featheresp32` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L508
