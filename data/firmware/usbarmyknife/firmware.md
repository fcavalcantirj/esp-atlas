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
  why: USB HID keystroke injection, mass-storage emulation and network-adapter impersonation all need the SoC's native USB peripheral
  board_signal: native-usb
sources:
- field: '*'
  url: https://github.com/i-am-shodan/USBArmyKnife
  verified: '2026-08-26'
- field: 'license'
  url: https://github.com/i-am-shodan/USBArmyKnife/blob/master/LICENSE
  verified: '2026-08-26'
- field: 'socs'
  url: https://github.com/i-am-shodan/USBArmyKnife#supported-hardware
  verified: '2026-08-26'
---

# USB Army Knife

A USB-based physical-access red-team tool: HID keystroke/mouse injection, mass-storage
emulation, network-adapter impersonation and Wi-Fi/Bluetooth attacks (via a forked ESP32
Marauder), all driven from a phone-friendly web UI. The LilyGO T-Dongle S3 is the
project's explicitly recommended hardware.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
