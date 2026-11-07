---
id: esp32marauder
type: firmware
name: ESP32 Marauder
url: https://github.com/justcallmekoko/ESP32Marauder
category: pentest
maintainer: justcallmekoko
socs:
- esp32
- esp32-c5
- esp32-c6
- esp32-s2
- esp32-s3
distribution:
- releases
- web-flasher
capabilities:
- wifi
- ble
benefits_from:
- display
- storage
requires:
- capability: wifi
  why: 2.4GHz Wi-Fi recon, on-chip
  board_signal: radio-wifi
- capability: ble
  why: BLE recon, on-chip
  board_signal: radio-ble
not_required:
- capability: psram
  why: capture buffers are small and fit the chip SRAM (Cardputer runs it with 0 PSRAM)
- capability: lora
  why: no LoRa in its toolset
popularity:
  stars: 13022
  forks: 1580
  as_of: '2026-11-07'
  github_repo_id: 208325027
  github_as_of: '2026-11-07T13:05:00Z'
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-01'
- field: socs
  url: https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1
  verified: '2026-09-07'
- field: socs
  url: https://github.com/justcallmekoko/ESP32Marauder/blob/master/.github/workflows/build_parallel.yml
  verified: '2026-09-07'
- field: summary
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-09-20'
- field: popularity.forks
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-11-07'
- field: popularity.github_as_of
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-11-07'
- field: popularity.github_repo_id
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-11-07'
- field: popularity.stars
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-11-07'
summary: "ESP32 Marauder is a firmware suite that provides a collection of offensive\
  \ and defensive Wi\u2011Fi and Bluetooth tools for ESP32 devices. It can be downloaded\
  \ as a release or purchased as a pre\u2011built unit."
readme_lang: en
readme_sha: 53b446c948feb01def43134748a591df2e958fbd12e54e4b63751bff9762aa8f
---

# ESP32 Marauder

ESP32 Marauder is a Wi-Fi and Bluetooth pentesting suite for a range of ESP32 boards. Its menu system is navigated on an onboard display, and it writes packet/PCAP captures to a microSD card.
