---
id: m5cardputer-adv__cypher-puter-os
type: recipe
board: m5cardputer-adv
firmware: cypher-puter-os
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the README names the Cardputer ADV as its target: 'Small, scriptable, and intentionally scoped to Cardputer ADV'. Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/dkyazzentwatwa/cypher-puter-os
  verified: '2026-11-15'
- field: board
  url: https://github.com/dkyazzentwatwa/cypher-puter-os/blob/2b16064409b18485ef4163d77f5bf4375982b5a3/README.md
  verified: '2026-11-15'
---

cypher-puter-os on the M5Stack Cardputer-Adv (ESP32-S3). `unverified`.

The project's own README targets the Cardputer ADV. That is source evidence of intended support,
not proof that today's code builds or runs: it has not been tested on hardware for this atlas.
