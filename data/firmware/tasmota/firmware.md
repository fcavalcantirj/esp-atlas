---
id: tasmota
type: firmware
name: Tasmota
url: https://github.com/arendst/Tasmota
category: home
maintainer: arendst
license: GPL-3.0
socs:
- esp32
- esp32-s2
- esp32-s3
- esp32-c3
- esp32-c6
distribution:
- releases
- web-flasher
capabilities:
- wifi
- mqtt
- on-device-web-ui
- ota
requires:
- capability: wifi
  why: serves its configuration web UI and MQTT/HTTP control over Wi-Fi
  board_signal: radio-wifi
not_required:
- capability: display
  why: fully configurable headless over its web UI; a screen is optional (some device
    templates add one)
popularity:
  stars: 24731
  downloads: 168
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/arendst/Tasmota
  verified: '2026-08-26'
- field: socs
  url: https://github.com/arendst/Tasmota/releases/tag/v15.6.0
  verified: '2026-08-26'
- field: distribution
  url: https://tasmota.github.io/install/
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/arendst/Tasmota
  verified: '2026-09-01'
---

# Tasmota

Tasmota is a mature, generic ESP32/ESP8266 firmware for local, cloud-free control over
MQTT, HTTP, Serial or KNX, configured through an on-device web UI with OTA updates and a
rules engine. The `v15.6.0` release ships generic `tasmota32*` binaries per SoC family
(`tasmota32`, `tasmota32s2`, `tasmota32s3`, `tasmota32c3`, `tasmota32c6`, plus per-language
variants) with no board-specific pin mapping required.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
