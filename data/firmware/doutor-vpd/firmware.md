---
id: doutor-vpd
type: firmware
name: Doutor VPD
url: https://github.com/fcavalcantirj/doutor-vpd-firmware
category: multi
maintainer: fcavalcantirj
socs:
- esp32-s3
distribution:
- releases
popularity:
  stars: 0
  forks: 0
  editorial_home: https://www.doutorvpd.com.br/
  as_of: '2026-10-21'
sources:
- field: '*'
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware
  verified: '2026-10-21'
- field: socs
  url: https://www.doutorvpd.com.br/
  verified: '2026-10-21'
- field: popularity
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware
  verified: '2026-10-21'
---

# Doutor VPD

Doutor VPD is firmware for an M5StickS3 with a Grove ENV III unit (SHT30): it reads the air,
computes VPD at the interval you choose, compares it with the target for the plant's stage and
shows the next step. It works with no account, no cloud and no Wi-Fi. Product site (pt-BR):
https://www.doutorvpd.com.br/

The releases repository publishes binaries only: each release carries `bootloader.bin`,
`partitions.bin`, `boot_app0.bin` and `firmware.bin`, plus a signed `manifest.json` /
`manifest.sig` that lists each image's offset and sha256.
