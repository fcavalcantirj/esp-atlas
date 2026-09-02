---
id: openmqttgateway
type: firmware
name: OpenMQTTGateway
url: https://github.com/1technophile/OpenMQTTGateway
category: home
maintainer: 1technophile
license: GPL-3.0
socs:
- esp32
- esp32-c3
- esp32-s3
distribution:
- releases
- web-flasher
capabilities:
- wifi
- mqtt
- ble
requires:
- capability: wifi
  why: bridges BLE/RF/IR sensors to an MQTT broker over Wi-Fi
  board_signal: radio-wifi
- capability: ble
  why: the BLE-to-MQTT gateway build decodes ~100 BLE sensor types
  board_signal: radio-ble
popularity:
  stars: 4082
  downloads: 385
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-08-26'
- field: socs
  url: https://docs.openmqttgateway.com/prerequisites/board.html
  verified: '2026-08-26'
- field: distribution
  url: https://docs.openmqttgateway.com/upload/web-install.html
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/1technophile/OpenMQTTGateway
  verified: '2026-09-01'
---

# OpenMQTTGateway

Unifies BLE, RF (433/315/868MHz), IR and other short-range protocols into a single
firmware that bridges everything to MQTT, integrating with Home Assistant, OpenHAB and
Node-RED. Ships PlatformIO environments per board/radio combo (e.g. `esp32c3-dev-m1-ble`
for a BLE gateway on the ESP32-C3-DevKitM-1) and a browser-based web installer.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
