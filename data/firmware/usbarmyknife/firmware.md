---
id: usbarmyknife
type: firmware
name: USB Army Knife
url: https://github.com/i-am-shodan/USBArmyKnife
category: badusb
maintainer: i-am-shodan
license: MIT
socs:
- esp32-s2
- esp32-s3
distribution:
- releases
capabilities:
- wifi
- ble
requires:
- capability: native-usb
  why: USB HID keystroke injection, mass-storage emulation and network-adapter impersonation
    all need the SoC's native USB peripheral
  board_signal: native-usb
popularity:
  stars: 2916
  forks: 282
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/i-am-shodan/USBArmyKnife
  verified: '2026-08-26'
- field: license
  url: https://github.com/i-am-shodan/USBArmyKnife/blob/master/LICENSE
  verified: '2026-08-26'
- field: socs
  url: https://github.com/i-am-shodan/USBArmyKnife#supported-hardware
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/i-am-shodan/USBArmyKnife
  verified: '2026-09-01'
- field: summary
  url: https://github.com/i-am-shodan/USBArmyKnife
  verified: '2026-09-20'
summary: "USB Army Knife is a compact ESP32\u2011based USB dongle that can emulate\
  \ HID keyboards, mass\u2011storage devices, and network adapters while performing\
  \ Wi\u2011Fi/Bluetooth attacks, all controllable via a web UI and a DuckyScript\u2011\
  compatible scripting engine for red\u2011team operations."
readme_lang: en
readme_sha: fe645441d79ac6d70668d22801ddda5be226aa70d074a1cee7a2645ae7e800f1
---

# USB Army Knife

A USB-based physical-access red-team tool: HID keystroke/mouse injection, mass-storage
emulation, network-adapter impersonation and Wi-Fi/Bluetooth attacks (via a forked ESP32
Marauder), all driven from a phone-friendly web UI. The LilyGO T-Dongle S3 is the
project's explicitly recommended hardware.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
