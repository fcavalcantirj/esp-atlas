---
id: m5stack-core2__stack-chan
type: recipe
board: m5stack-core2
firmware: stack-chan
status: unverified
chip_family: esp32
notes: "stack-chan names this board as m5stack_core2 in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/stack-chan/stack-chan
  verified: '2026-09-22'
- field: board
  url: https://github.com/stack-chan/stack-chan/blob/develop/.github/workflows/bundle.yml
  verified: '2026-09-22'
---

# m5stack-core2 x stack-chan

`stack-chan` declares `m5stack_core2` in its CI matrix; that name resolves to the catalogued board `m5stack-core2` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `m5stack_core2` — https://github.com/stack-chan/stack-chan/blob/develop/.github/workflows/bundle.yml
