---
id: esp32-s31
type: soc
vendor: espressif
name: ESP32-S31
cpu:
  arch: risc-v
  cores: 2
  max_mhz: 320
  extensions:
  - fpu
  - simd-vector
  lp_core:
    arch: risc-v
    max_mhz: 40
memory:
  sram_kb: 512
  lp_sram_kb: 32
  rom_kb: 320
  in_package_psram_mb:
  - 16
  - 32
  psram_external: true
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.4'
    classic: true
    features:
    - le-audio
    - direction-finding-aoa-aod
    - pawr
    - mesh-1.1
  ieee802154:
    present: true
    protocols:
    - thread-1.4
    - zigbee-3.0
usb:
  native: true
  type: usb-2.0-high-speed-otg + serial-jtag
interfaces:
- ethernet-mac-1000mbps-rmii-mii
- dvp-camera-8to16bit
- lcd-parallel-rgb-i8080-moto6800-8to24bit
- capacitive-touch-14ch
- i2s-dual
security:
- secure-boot
- flash-psram-encryption-xts-aes
- aes
- sha
- rsa
- ecc
- hmac
- rsa-ecdsa-ds
- trng
- puf
- secure-debug-controller
- key-manager
- apm
- tee
- glitch-detector
drive:
  gpio_pads_total: 60
reserved_pins:
  strapping:
  - 37
  - 60
  - 61
  usb_flash_tied:
  - 33
  - 34
  - 36
  - 37
  - 38
  - 40
  - 41
  - 42
notes:
- Wi-Fi 6 (802.11ax), 2.4 GHz only, 1T1R; backward compatible with 802.11b/g/n up
  to 150 Mbps
- Bluetooth 5.4 with both LE (Mesh 1.1, LE Audio, Direction Finding AoA/AoD, PAwR)
  and Classic BR/EDR
- Integrated 1000 Mbps Ethernet MAC (RMII/MII); needs an external PHY
- In-package octal PSRAM (16 or 32 MB) is not bonded out to separate GPIOs; the
  chip also supports external flash/PSRAM (up to 256 MB flash, 64 MB PSRAM) via
  SPI/Dual/Quad/Octal
- No per-pad IOH/IOL current table published in the datasheet as of 2026-08-26 --
  gpio_source_ma_max/gpio_sink_ma_max omitted, not guessed. gpio_pads_total=60 is
  the datasheet's stated GPIO count (8 LP GPIO + 52 HP GPIO).
- 'Default drive strength: GPIO33/34 = 40 mA, others 20 mA (DRV levels 0-3 correspond
  to ~5/10/20/40 mA).'
- GPIO33/34 are USB Serial/JTAG D-/D+ by default; GPIO36-38,40-42 are tied to the
  off-package SPI flash (SPICS/SPIQ/SPIWP/SPIHD/SPICLK/SPID); GPIO37 doubles as
  both a strapping pin and the flash SPIQ signal.
- No physically input-only GPIO stated in the Hardware Design Guidelines (GPIO13/RMII_CLK
  is input-only only in that one alternate function, not an inherent pad limitation)
  -- input_only omitted, not guessed.
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-s31_datasheet_en.html
  verified: '2026-08-26'
- field: '*'
  url: https://www.espressif.com/en/products/socs/esp32-s31
  verified: '2026-08-26'
- field: drive
  url: https://documentation.espressif.com/esp32-s31_datasheet_en.html
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s31/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-S31

Dual-core RISC-V @ 320 MHz with SIMD/FPU, Wi-Fi 6, Bluetooth 5.4 (LE + Classic),
802.15.4 (Thread/Zigbee), and an integrated 1000 Mbps Ethernet MAC -- Espressif's
newest multi-protocol HMI/connectivity chip.
