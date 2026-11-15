---
id: m5cardputer-adv__meshcore-cardputer
type: recipe
board: m5cardputer-adv
firmware: meshcore-cardputer
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the README targets the M5Stack Cardputer ADV with the Cap LoRa-1262 and says 'the original Cardputer is not supported yet'; every build env and release asset is named cardputer_adv_*. Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/arthubhub/meshcore-cardputer
  verified: '2026-11-15'
- field: board
  url: https://github.com/arthubhub/meshcore-cardputer/blob/313b4cf8a1613a8551a2bed0f10336ef876e3dcf/README.md
  verified: '2026-11-15'
---

meshcore-cardputer on the M5Stack Cardputer-Adv (ESP32-S3). `unverified`.

The project's README targets the Cardputer ADV and states the original Cardputer is not supported yet.
That is source evidence of intended support, not proof that today's code builds or runs.
