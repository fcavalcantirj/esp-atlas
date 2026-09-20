---
id: wled
type: firmware
name: WLED
url: https://github.com/wled/WLED
category: home
maintainer: wled
license: EUPL-1.2
socs:
- esp32
- esp32-c3
- esp32-c5
- esp32-c6
- esp32-s2
- esp32-s3
distribution:
- releases
- web-flasher
- esp-web-tools
capabilities:
- wifi
- on-device-web-ui
- mqtt
- e131
- artnet
- ddp
- ota
requires:
- capability: wifi
  why: serves its web UI over Wi-Fi
  board_signal: radio-wifi
not_required:
- capability: psram
  why: web assets fit in 4MB flash
- capability: display
  why: no screen needed
- capability: ble
- capability: storage
popularity:
  stars: 18691
  forks: 4357
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/wled/WLED
  verified: '2026-08-24'
- field: license
  url: https://raw.githubusercontent.com/wled/WLED/main/LICENSE
  verified: '2026-08-24'
- field: socs
  url: https://raw.githubusercontent.com/wled/WLED/main/platformio.ini
  verified: '2026-08-24'
- field: distribution
  url: https://install.wled.me/
  verified: '2026-08-24'
- field: popularity
  url: https://github.com/wled/WLED
  verified: '2026-09-01'
- field: socs
  url: https://github.com/wled/WLED/blob/main/platformio.ini#L552
  verified: '2026-09-07'
- field: summary
  url: https://github.com/wled/WLED
  verified: '2026-09-20'
summary: "WLED is a fast, feature\u2011rich firmware for ESP32 microcontrollers that\
  \ enables control of addressable LED strips, 2D matrices, and HUB75 panels, offering\
  \ hundreds of built\u2011in effects, segment management, OTA updates, and extensive\
  \ integration options."
readme_lang: en
readme_sha: c34e3c966bb25ca2a3ae407a3bbeae677a3bb8abd1b313613616da63aea9a334
---

# WLED

WLED drives addressable LED strips from an ESP32 and serves its own web UI for effects,
segments and presets, with MQTT, E1.31/Art-Net/DDP and Home Assistant integration.
The project's installer at install.wled.me flashes the official builds in the browser.

No `manifest_url` is recorded: the manifests install.wled.me serves are per-release (the
stable one still pins 0.15.3) and route binaries through a third-party CORS proxy, so there
is no canonical, current manifest URL to cite.
