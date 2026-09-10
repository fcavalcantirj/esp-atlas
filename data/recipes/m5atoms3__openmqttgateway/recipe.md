---
id: m5atoms3__openmqttgateway
type: recipe
board: m5atoms3
firmware: openmqttgateway
status: unverified
chip_family: esp32-s3
flash:
  env: "esp32s3-atomS3U"
notes: "openmqttgateway names this board as m5stack-atoms3 in its platformio.ini (env esp32s3-atomS3U); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-10'
- field: flash.env
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1943
  verified: '2026-09-10'
- field: board
  url: https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1943
  verified: '2026-09-10'
---

# m5atoms3 x openmqttgateway

`openmqttgateway` declares `m5stack-atoms3` in its platformio.ini; that name resolves to the catalogued board `m5atoms3` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `m5stack-atoms3` — https://github.com/1technophile/OpenMQTTGateway/blob/development/environments.ini#L1943
