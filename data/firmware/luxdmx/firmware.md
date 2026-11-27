---
id: luxdmx
type: firmware
name: LuxDMX
url: https://github.com/tombueng/LuxDMX
category: home
maintainer: tombueng
capabilities:
- e131
- ethernet
- on-device-web-ui
popularity:
  stars: 104
  forks: 7
  github_as_of: '2026-11-27'
  downloads: 0
  downloads_as_of: '2026-11-27'
  editorial_home: https://luxdmx.org
  editorial_home_as_of: '2026-11-27'
  as_of: '2026-11-27'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/tombueng/LuxDMX
  verified: '2026-11-27'
- field: popularity.github_as_of
  url: https://github.com/tombueng/LuxDMX
  verified: '2026-11-27'
- field: popularity.stars
  url: https://github.com/tombueng/LuxDMX
  verified: '2026-11-27'
- field: popularity.forks
  url: https://github.com/tombueng/LuxDMX
  verified: '2026-11-27'
- field: popularity.downloads
  url: https://api.launcherhub.net/giveMeTheList
  verified: '2026-11-27'
- field: popularity.downloads_as_of
  url: https://api.launcherhub.net/giveMeTheList
  verified: '2026-11-27'
- field: popularity.editorial_home
  url: https://luxdmx.org
  verified: '2026-11-27'
- field: popularity.editorial_home_as_of
  url: https://luxdmx.org
  verified: '2026-11-27'
---

Open-source Art-Net / sACN (E1.31) → DMX512 gateway for ESP32 / ESP32-S3 / Ethernet. Live web UI shows all 512 channels in real time, flags console conflicts, and drives galvanically-isolated DMX. Flash from your browser, no toolchain.
