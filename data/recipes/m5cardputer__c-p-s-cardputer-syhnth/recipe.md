---
id: m5cardputer__c-p-s-cardputer-syhnth
type: recipe
board: m5cardputer
firmware: c-p-s-cardputer-syhnth
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the C.P.S. README says it targets the M5Stack Cardputer family (Cardputer ADV and the original Cardputer) and that original-Cardputer support was added, with the missing IMU auto-detected at boot (commit 1931da2). The upstream author explicitly says they have not personally tested the original Cardputer; it has a three-key rollover limit and substitutes key-driven PAD control for the missing IMU. Some features, such as the arpeggiator, are Cardputer ADV only. Its platformio.ini builds against the generic esp32-s3-devkitc-1 board definition, not a Cardputer-specific one. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/oldtokage-collab/C.P.S.--Cardputer-SYHNTH--
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/oldtokage-collab/C.P.S.--Cardputer-SYHNTH--/blob/1931da267bdec85ccbd6ccec8be1a4ff6d195878/README.md
  verified: '2026-11-05'
---

C.P.S. (CardPuter Synth) on the M5Stack Cardputer (ESP32-S3). `unverified`.

The README names the original Cardputer as supported alongside the Cardputer ADV;
on the original Cardputer, which has no IMU, the synth falls back to key-driven
control, and ADV-only features like the arpeggiator are unavailable. No current
successful build has been confirmed, and it has not been tested on hardware for
this atlas.
