---
id: m5stack-fire__clawdmeter
type: recipe
board: m5stack-fire
firmware: clawdmeter
status: unverified
chip_family: esp32
flash:
  method: release-bin
notes: "clawdmeter names this board as m5stack_fire in its release (asset m5stack_fire-v2.2.5.bin) (release v2.2.5); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/HermannBjorgvin/Clawdmeter
  verified: '2026-11-03'
- field: board
  url: https://github.com/HermannBjorgvin/Clawdmeter/releases/tag/v2.2.5
  verified: '2026-11-03'
---

# m5stack-fire x clawdmeter

`clawdmeter` declares `m5stack_fire` in its release; that name resolves to the catalogued board `m5stack-fire` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `m5stack_fire` — https://github.com/HermannBjorgvin/Clawdmeter/releases/download/v2.2.5/m5stack_fire-v2.2.5.bin
