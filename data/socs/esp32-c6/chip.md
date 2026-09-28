---
id: esp32-c6
type: soc
vendor: espressif
name: ESP32-C6
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 160
  lp_core:
    arch: risc-v
    max_mhz: 20
memory:
  sram_kb: 512
  lp_sram_kb: 16
  rom_kb: 320
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.3'
    classic: false
  ieee802154:
    present: true
    protocols:
    - zigbee-3.0
    - thread-1.3
    - matter
usb:
  native: true
  type: serial-jtag
security:
- secure-boot
- flash-encryption-xts-aes
- aes-256
- ecc
- hmac
- rsa
- sha
- rsa-ds
- rng
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 30
reserved_pins:
  strapping:
  - 8
  - 9
  - 10
  - 11
  - 15
  usb_flash_tied:
  - 12
  - 13
notes:
- Wi-Fi / BLE / 802.15.4 coexist on a shared antenna
- 'Default drive strength: GPIO12/13 = 40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-21'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/schematic-checklist.html
  verified: '2026-08-26'
- field: drive
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-26'
---

# ESP32-C6

The IoT all-rounder: **Wi-Fi 6 + BLE 5.3 + 802.15.4 (Zigbee 3.0 / Thread 1.3 / Matter)** in one chip, plus a low-power RISC-V core. The single-chip smart-home pick.

Espressif's own datasheet describes the ESP32-C6 as "a low-power and cost-effective 2.4 GHz Wi-Fi 6 + Bluetooth 5 (LE) + Thread/Zigbee SoC, with a 32-bit RISC-V core, for securely connected devices." It is the successor to the ESP32-C3 in Espressif's single-core RISC-V line, and the first Espressif chip to combine Wi-Fi 6 with an 802.15.4 radio, which makes it the reference part for Matter-over-Thread and Matter-over-Wi-Fi end devices that also need a classic Wi-Fi fallback.

## CPU and memory

The ESP32-C6 carries two 32-bit RISC-V cores. The high-performance (HP) core is a 4-stage-pipeline design clocked up to 160 MHz and runs the main application, Wi-Fi/BLE/802.15.4 stacks, and ESP-IDF. A separate low-power (LP) core, a simpler 2-stage-pipeline RISC-V design clocked up to 20 MHz, can keep running sensor polling, timers, or simple logic while the HP core is powered down, which is what makes the chip's deep-sleep current so low. On-chip memory is 512 KB of HP SRAM plus a dedicated 16 KB LP SRAM (reachable by either core) for code and data, backed by 320 KB of mask ROM for boot and core routines.

## Radio stack

All three radios share a single 2.4 GHz antenna (time-multiplexed, not simultaneous):

- **Wi-Fi 6 (802.11ax)**, 2.4 GHz only, 1T1R, with data rates up to 150 Mbps and backward compatibility with 802.11b/g/n. Wi-Fi 6's Target Wake Time (TWT) lets battery-powered nodes negotiate wake schedules with the access point, which is the main reason Wi-Fi 6 lowers average power draw versus 802.11n on comparable traffic.
- **Bluetooth LE 5.3** (certified), LE only — there is no Bluetooth Classic on this chip.
- **IEEE 802.15.4-2015** radio, running either a **Zigbee 3.0** or a **Thread 1.3** network stack. Combined with the Wi-Fi and BLE radios, this is what lets the ESP32-C6 act as a Matter-compliant Wi-Fi end device or a Matter-over-Thread end device from the same silicon.

## GPIO and peripherals

The standard QFN40 package exposes up to 30 GPIO pads (a smaller QFN32 variant exposes 22); a handful are reserved as strapping pins or tied to off-chip flash/USB signals — see `reserved_pins` in this record. Peripheral set: a 12-bit SAR ADC with up to 7 channels, two general-purpose UARTs plus an LP UART, a general SPI controller plus two dedicated SPI buses for external flash/PSRAM, I2C and LP I2C, I2S, two TWAI (CAN 2.0-compatible) controllers, an SDIO slave, LED PWM (up to 6 channels), MCPWM, RMT, and PARLIO. USB connectivity is via the native USB Serial/JTAG controller — flashing, console, and JTAG debugging over a single USB connection, no external USB-to-serial bridge chip required.

## Low-power design

Alongside Active mode, the ESP32-C6 supports Modem-sleep, Light-sleep, and Deep-sleep. In Deep-sleep, Espressif specifies power consumption as low as 7 µA, with the LP core and LP SRAM still able to run and wake the HP core on a timer, GPIO, or other event. This power profile, combined with Wi-Fi 6 TWT and 802.15.4's naturally low duty cycles, is what Espressif targets at coin-cell and battery-powered sensor/end-node designs.

## Security

Hardware security features include RSA-3072-based secure boot, AES-128/256-XTS flash encryption, ECC, HMAC, SHA, and an RSA digital-signature peripheral, plus a hardware RNG — see the `security` field above for the full list as tracked in this record. Cryptographic key material is backed by 4096 bits of eFuse (1792 bits available to users), Espressif's one-time-programmable storage for keys and device identity.

## Typical use cases

Espressif's stated application targets for the ESP32-C6 include smart home, industrial automation, healthcare, consumer electronics, smart agriculture, POS machines, service robots, audio devices, and generic low-power IoT sensor hubs and data loggers. In practice the chip's combination of Wi-Fi 6, BLE, and 802.15.4 on one die makes it most common as a Matter/Thread border-adjacent end device or Zigbee end device in smart-home and building-automation products, and as a Wi-Fi sensor node where Target Wake Time and deep-sleep current matter for battery life.
