---
id: esp32-p4
type: soc
vendor: espressif
name: ESP32-P4
cpu:
  arch: risc-v
  cores: 2
  max_mhz: 400
  extensions:
  - fpu
  - ai
  lp_core:
    arch: risc-v
    max_mhz: 40
memory:
  sram_kb: 768
  lp_sram_kb: 32
  in_package_psram_mb:
  - 16
  - 32
  psram_external: true
radios:
  wifi: null
  bluetooth: null
  ieee802154:
    present: false
usb:
  native: true
  type: usb-2.0-high-speed-otg
interfaces:
- mipi-csi-camera-isp-1080p
- mipi-dsi-display-1080p
- ethernet-emac-rmii
- h264-encode-1080p30
security:
- secure-boot
- flash-encryption
- crypto-accelerators
- trng
- ds-peripheral
- key-management-unit
notes:
- No integrated Wi-Fi / Bluetooth / 802.15.4 — external companion radio required (commonly
  paired with an ESP32-C6; that pairing is an Espressif design recommendation, not
  a P4 datasheet spec)
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-p4_datasheet_en.html
  verified: '2026-08-21'
---

# ESP32-P4

The compute/HMI powerhouse: dual-core RISC-V @ 400 MHz with FPU + AI extensions, MIPI camera & display, USB 2.0 High-Speed, Ethernet, and H.264 encode. **No wireless of any kind** — it needs an external companion radio for connectivity.
