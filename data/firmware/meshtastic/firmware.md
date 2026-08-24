---
id: meshtastic
type: firmware
name: Meshtastic
url: https://github.com/meshtastic/firmware
category: mesh
maintainer: meshtastic
license: GPL-3.0-only
socs:
- esp32
- esp32-s3
- esp32-c3
- esp32-c6
distribution:
- releases
- web-flasher
capabilities:
- lora
- mesh
- ble
- wifi
- gps
- telemetry
sources:
- field: '*'
  url: https://github.com/meshtastic/firmware
  verified: '2026-08-24'
- field: 'license'
  url: https://raw.githubusercontent.com/meshtastic/firmware/master/LICENSE
  verified: '2026-08-24'
- field: 'distribution'
  url: https://flasher.meshtastic.org/
  verified: '2026-08-24'
- field: 'socs'
  url: https://github.com/meshtastic/firmware/tree/master/variants/esp32s3
  verified: '2026-08-24'
---

# Meshtastic

Meshtastic turns LoRa-equipped ESP32 boards into an off-grid mesh for text messaging,
position sharing and telemetry, paired to a phone over Bluetooth. The official browser
flasher at flasher.meshtastic.org writes the per-device builds.

A board needs a LoRa radio to join the mesh: several build targets below are for boards
whose radio comes from an add-on module rather than the board itself, which each recipe notes.
