---
id: esphome
type: firmware
name: ESPHome
url: https://github.com/esphome/esphome
category: home
maintainer: esphome
license: MIT AND GPL-3.0-only
socs:
- esp32
- esp32-s2
- esp32-s3
- esp32-c2
- esp32-c3
- esp32-c5
- esp32-c6
- esp32-h2
- esp32-p4
distribution:
- web-flasher
- esp-web-tools
capabilities:
- wifi
- ethernet
- ble
- bluetooth-proxy
- mqtt
- ota
- on-device-web-ui
- display
requires:
- capability: wifi
  why: reports to Home Assistant over Wi-Fi (or Ethernet)
  board_signal: radio-wifi
not_required:
- capability: psram
  why: NOT needed for small/no-display configs — but IS needed when driving a large display framebuffer that exceeds the ~520KB ESP32 SRAM (e.g. the 9.7in Inkplate-10, which ships 8MB PSRAM). PSRAM need depends on the board framebuffer size, not the firmware
sources:
- field: '*'
  url: https://github.com/esphome/esphome
  verified: '2026-08-24'
- field: 'license'
  url: https://github.com/esphome/esphome/blob/dev/LICENSE
  verified: '2026-08-24'
- field: 'socs'
  url: https://esphome.io/components/esp32.html
  verified: '2026-08-24'
- field: 'distribution'
  url: https://web.esphome.io/
  verified: '2026-08-24'
---

# ESPHome

ESPHome compiles a YAML device description into ESP32 firmware, most often to expose the
board to Home Assistant. Firmware is built per user configuration rather than shipped as a
fixed binary, so there is no release download: web.esphome.io flashes the build in the browser.

Because ESPHome targets the chip rather than a specific product, the recipes below are only
the boards a fetchable page names explicitly. Entries cited to devices.esphome.io land as
`reported`: that catalogue is community-maintained, not maintainer-verified.
