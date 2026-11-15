---
id: m5cardputer-adv__glide-synth-cardputer-adv
type: recipe
board: m5cardputer-adv
firmware: glide-synth-cardputer-adv
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the README says 'Firmware for the M5Stack Cardputer, original (v1.1) and ADV.' The original Cardputer has its own recipe (m5cardputer__glide-synth-cardputer-adv). Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/CHARL3X/GLIDE-Synth-Cardputer-ADV
  verified: '2026-11-15'
- field: board
  url: https://github.com/CHARL3X/GLIDE-Synth-Cardputer-ADV/blob/473e346eb95468825d57f77daf19364376344be1/README.md
  verified: '2026-11-15'
---

glide-synth-cardputer-adv on the M5Stack Cardputer-Adv (ESP32-S3). `unverified`.

The README names both the original Cardputer (v1.1) and the ADV as targets. That is source evidence of
intended support, not proof that today's code builds or runs: it has not been tested on hardware here.
