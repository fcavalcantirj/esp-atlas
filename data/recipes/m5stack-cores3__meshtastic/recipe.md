---
id: m5stack-cores3__meshtastic
type: recipe
board: m5stack-cores3
firmware: meshtastic
status: known-good
chip_family: esp32-s3
flash:
  method: web-flasher
notes: "Official firmware build target `m5stack_cores3`, but the CoreS3 carries no LoRa radio: it needs an external SX126x module to join a mesh."
sources:
- field: '*'
  url: https://github.com/meshtastic/firmware/tree/master/variants/esp32s3
  verified: '2026-08-24'
---

# m5stack-cores3 x meshtastic

Official firmware build target `m5stack_cores3`, but the CoreS3 carries no LoRa radio: it needs an external SX126x module to join a mesh.
