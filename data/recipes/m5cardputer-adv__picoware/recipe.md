---
id: m5cardputer-adv__picoware
type: recipe
board: m5cardputer-adv
firmware: picoware
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the README names the Cardputer ADV as its target: 'Open-source custom firmware for PicoCalc, Cardputer ADV, Flipper Zero, POOM, and other ESP32/Raspberry Pi Pico devices'. Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/jblanked/Picoware
  verified: '2026-11-15'
- field: board
  url: https://github.com/jblanked/Picoware/blob/8915fbe7b68059f96e4f99730ad3383da7a77a38/README.md
  verified: '2026-11-15'
---

picoware on the M5Stack Cardputer-Adv (ESP32-S3). `unverified`.

The project's own README targets the Cardputer ADV. That is source evidence of intended support,
not proof that today's code builds or runs: it has not been tested on hardware for this atlas.
