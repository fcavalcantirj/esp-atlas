---
id: esp32marauder
type: firmware
name: ESP32 Marauder
url: https://github.com/justcallmekoko/ESP32Marauder
category: pentest
maintainer: justcallmekoko
socs:
- esp32
- esp32-s2
- esp32-s3
- esp32-c5
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
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-08-23'
---

# ESP32 Marauder

ESP32 Marauder is a Wi-Fi and Bluetooth pentesting suite for a range of ESP32 boards. Its menu system is navigated on an onboard display, and it writes packet/PCAP captures to a microSD card.
