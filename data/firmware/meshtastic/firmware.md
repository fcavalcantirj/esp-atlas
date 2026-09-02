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
benefits_from:
- gps
- display
requires:
- capability: lora
  why: off-grid mesh runs on a LoRa transceiver the ESP32 chip lacks; the board must
    carry an SX126x/SX127x
  board_signal: lora
- capability: ble
  why: pairs to a phone over BLE
  board_signal: radio-ble
not_required:
- capability: psram
  why: small text/telemetry payloads
- capability: display
  why: headless nodes are fine; a screen is optional
popularity:
  stars: 8240
  downloads: 651
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/meshtastic/firmware
  verified: '2026-08-24'
- field: license
  url: https://raw.githubusercontent.com/meshtastic/firmware/master/LICENSE
  verified: '2026-08-24'
- field: distribution
  url: https://flasher.meshtastic.org/
  verified: '2026-08-24'
- field: socs
  url: https://github.com/meshtastic/firmware/tree/master/variants/esp32s3
  verified: '2026-08-24'
- field: popularity
  url: https://github.com/meshtastic/firmware
  verified: '2026-09-01'
---

# Meshtastic

Meshtastic turns LoRa-equipped ESP32 boards into an off-grid mesh for text messaging,
position sharing and telemetry, paired to a phone over Bluetooth. The official browser
flasher at flasher.meshtastic.org writes the per-device builds.

A board needs a LoRa radio to join the mesh: several build targets below are for boards
whose radio comes from an add-on module rather than the board itself, which each recipe notes.
