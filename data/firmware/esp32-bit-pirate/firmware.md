---
id: esp32-bit-pirate
type: firmware
name: ESP32 Bit Pirate
url: https://github.com/geo-tp/ESP32-Bit-Pirate
category: pentest
maintainer: geo-tp
license: MIT
socs:
- esp32-s3
distribution:
- releases
- web-flasher
- m5burner
capabilities:
- wifi
- ble
requires:
- capability: wifi
  why: Wi-Fi mode (sniff/deauth/nmap/netcat) and the web CLI need the SoC's Wi-Fi
    radio
  board_signal: radio-wifi
popularity:
  stars: 5674
  downloads: 164
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-08-26'
- field: license
  url: https://github.com/geo-tp/ESP32-Bit-Pirate/blob/main/LICENSE
  verified: '2026-08-26'
- field: distribution
  url: https://geo-tp.github.io/ESP32-Bit-Pirate/webflasher/
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-01'
---

# ESP32 Bit Pirate

A Bus-Pirate-inspired multi-protocol hardware-hacking firmware: I2C/SPI/UART/1-Wire/CAN/
JTAG bus tools, plus Wi-Fi, Bluetooth, Sub-GHz, RFID and IR radio modes, driven from a
serial terminal or a web-based CLI. Runs on any ESP32-S3 board with >=8MB flash; the
project explicitly lists the M5 Cardputer among its supported devices.

Was formerly named ESP32-Bus-Pirate (GitHub redirects the old name to this repo).

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
