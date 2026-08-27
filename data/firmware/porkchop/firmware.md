---
id: porkchop
type: firmware
name: M5PORKCHOP
url: https://github.com/0ct0sec/M5PORKCHOP
category: pentest
maintainer: 0ct0sec
capabilities:
- "promiscuous Wi\u2011Fi packet capture and EAPOL extraction"
- GPS wardriving with WiGLE export
- "2.4\u202FGHz spectrum analysis with client tracking"
- BLE notification spam (Apple/Android/Samsung/Windows)
- Beacon injection with vendor IE fingerprinting
- "ESP\u2011NOW device\u2011to\u2011device sync (PigSync)"
- file manager over HTTP (SD card)
- personality system with mood, avatar, weather effects
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/0ct0sec/M5PORKCHOP
  verified: '2026-08-27'
---

M5PORKCHOP is a WiFi pentesting companion firmware for the M5Cardputer (ESP32‑S3). It provides promiscuous packet capture, EAPOL extraction, GPS wardriving, spectrum analysis, BLE spam, beacon injection, ESP‑NOW sync, and a personality system. See README for full feature list.
