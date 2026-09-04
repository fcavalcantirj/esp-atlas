---
id: m5cardputer__ruview
type: recipe
board: m5cardputer
firmware: ruview
status: unverified
chip_family: esp32-s3
notes: "Weakest of the three RuView recipes, and deliberately labelled as such. RuView's own repo says nothing about the M5Stack Cardputer — no README mention, no build overlay, no release asset naming it. The only evidence is a third-party entry in the Launcher/M5Burner community catalog (`api.launcherhub.net/giveMeTheList`, fid e6ddd6ee4d27df6a0d04e072b2b78312) published by author `runtz`, listing name \"RuView\", category `cardputer`, esp `s3`, 126 downloads, 0 stars, pointing at RuView's own `v0.8.3-esp32` release tag. That catalog is marked DISCOVERY ONLY in seeds.json — a signal that something exists, not a maintainer's support claim. The pairing is chip-plausible (Cardputer is an esp32-s3 with 8 MB flash, and RuView's default build compiles display support in, so a screened board is the default target rather than the exception) but nothing upstream confirms it. No `flash` block: no Cardputer-specific artifact exists to cite, and RuView's generic install is a four-file bundle write, not a single merged image."
sources:
- field: '*'
  url: https://github.com/ruvnet/RuView
  verified: '2026-09-04'
- field: 'board'
  url: https://api.launcherhub.net/giveMeTheList
  verified: '2026-09-04'
---

# m5cardputer x ruview

**Treat this one as a lead, not a recipe.** RuView's repository never mentions
the Cardputer — no README line, no build overlay, no release asset named for it.

What does exist is a community upload: the Launcher/M5Burner catalog carries an
entry called "RuView" (author `runtz`, category `cardputer`, chip `s3`, 126
downloads) pointing back at RuView's own `v0.8.3-esp32` release tag. This atlas
treats that catalog as a discovery signal only, never as a maintainer's support
claim.

The pairing is at least chip-plausible: the Cardputer is an ESP32-S3 with 8 MB of
flash, and RuView's default build compiles display support in — so a board with a
screen is the ordinary target, not a special case. That is reasoning, not
evidence.

No flash instructions are recorded here because no Cardputer-specific artifact
exists to point at. If you want to try it, start from the generic ESP32-S3 path —
the `esp32-s3-devkitc-1` recipe for this firmware spells it out — but take the
`s3-8mb` bundle rather than the 4 MB one, since the Cardputer carries 8 MB, and
expect to sort out the display and keyboard yourself.

`unverified` — and the board pairing itself is uncited.
