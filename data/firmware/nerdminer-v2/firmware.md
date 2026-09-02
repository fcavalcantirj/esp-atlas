---
id: nerdminer-v2
type: firmware
name: NerdMiner v2
url: https://github.com/BitMaker-hub/NerdMiner_v2
category: display
maintainer: BitMaker-hub
license: MIT
socs:
- esp32
- esp32-s2
- esp32-s3
- esp32-c3
distribution:
- releases
capabilities:
- wifi
- display
requires:
- capability: wifi
  why: mines against a Stratum solo pool (default public-pool.io) over Wi-Fi
  board_signal: radio-wifi
- capability: display
  why: its whole purpose is showing mining/clock/global-stats screens
  board_signal: display
popularity:
  stars: 2785
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-08-26'
- field: license
  url: https://raw.githubusercontent.com/BitMaker-hub/NerdMiner_v2/main/LICENSE
  verified: '2026-08-26'
- field: socs
  url: https://github.com/BitMaker-hub/NerdMiner_v2/releases/tag/nerdminer-release-V1.8.3
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-09-01'
---

# NerdMiner v2

A solo-mining desk toy: implements the Stratum protocol against a solo pool
(public-pool.io by default) and cycles through NerdMiner/ClockMiner/GlobalStats screens.
Not a serious miner (low share difficulty means it's rarely seen by standard pools) — it's
a hardware-hacking learning project and a fun screen widget. Supports a long, growing list
of ESP32/S2/S3/C3 boards, including a factory image for the M5StickC Plus2.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
