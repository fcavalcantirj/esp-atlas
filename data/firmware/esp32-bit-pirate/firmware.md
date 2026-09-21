---
id: esp32-bit-pirate
type: firmware
name: ESP32 Bit Pirate
url: https://github.com/geo-tp/ESP32-Bit-Pirate
category: pentest
maintainer: geo-tp
license: MIT
socs:
- esp32
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
  stars: 5876
  forks: 487
  as_of: '2026-09-20'
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
- field: summary
  url: https://github.com/geo-tp/ESP32-Bit-Pirate
  verified: '2026-09-20'
- field: socs
  url: https://github.com/geo-tp/ESP32-Bit-Pirate#readme
  verified: '2026-09-21'
summary: "ESP32 Bus Pirate is an open\u2011source firmware for ESP32\u2011S3 devices\
  \ that turns the hardware into a multi\u2011protocol hacking tool, offering an interactive\
  \ CLI over USB serial or Wi\u2011Fi to sniff, send, script and control numerous\
  \ digital (I2C, SPI, UART, 1\u2011Wire, etc.) and radio (Bluetooth, Wi\u2011Fi,\
  \ Sub\u2011GHz, RFID) protocols."
readme_lang: en
readme_sha: 136a23af18ea925eea22f10e2e556cc07ff2d7ef7a26b8284679e136445f404a
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
