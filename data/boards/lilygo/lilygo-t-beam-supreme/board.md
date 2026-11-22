---
id: lilygo-t-beam-supreme
type: board
brand: lilygo
name: T-Beam Supreme
aka:
- T-Beam S3 Supreme
soc: esp32-s3
flash_mb: 8
psram_mb: 8
form_factor: t-beam
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
display: OLED SH1106
extras:
- lora
- gps
- imu
- magnetometer
- rtc
- sd-card
- qwiic
notes:
- 'ESP32-S3FN8 with 8 MB flash and 8 MB PSRAM: the product page lists "ESP32-S3FN8 Dual-core
  LX7 microprocessor" with Flash 8MB and PSRAM 8MB, and LILYGO''s hardware doc lists
  both T-Beam S3 Supreme builds as "ESP32-S3FN8 | 8MB(Quad-SPI) | 8MB(Quad-SPI)". The
  FN8 part has no in-package PSRAM; the core-board schematic carries the separate PSRAM/flash
  footprint'
- 'Wireless: the product page reads "2.4 GHz Wi-Fi & Bluetooth5 (LE)"'
- 'LoRa radio is SKU-dependent: the hardware doc gives "RF  Module | SX1262" at "Frequency
  range | 868/915MHz" and "RF  Module | LR1121" (sub-GHz and 2.4 GHz), and notes "Radio
  has its own SPI bus, and other peripheral SPI devices share the SPI bus." LILYGO''s
  separate 144-148 MHz hardware page uses an SX1278 ("Frequency range | 144-148MHz").
  The product page sells it as one listing with L76K or UBLOX GNSS at 433, 868, 915 or
  920 MHz, plus "L76K 144~148 MHz"'
- 'GNSS is SKU-dependent: the hardware doc names the builds "T-Beam S3 Supreme L76K"
  and "T-Beam S3 Supreme Ublox" (u-blox MAX-M10) and notes "GNSS Wake-up is only available
  in L76K version"; "T-Beam Supreme GPS backup power comes from 18650 battery"'
- 'Sensors: six-axis IMU QMI8658 (product page "Six-axis IMU QMI8658"), PCF8563 RTC,
  BME280 temperature/humidity sensor, and a magnetometer that varies by build: "T-BeamSupreme
  has three magnetometer versions: QMC6310N, QMC6310U, and QMC6309, each with a different
  device address."'
- 'Power: AXP2101 PMU; the hardware doc gives "USB-C Input Voltage | 3.9V-6V" and "Charge
  Current | 0-1024mA" for the 3.7V 18650 cell held on the board'
- 'usb.bridge=native DERIVED: neither LILYGO schematic (T-Beam-S3-Core, T-Beam-S3-Supreme-V3.1)
  carries a USB-UART bridge chip; the USB-C data lines run as USB_DP/USB_DM to the ESP32-S3,
  and the hardware doc''s Arduino settings use "USB CDC On Boot | Enable" with USB Mode
  "CDC and JTAG". usb_serial derived from usb.bridge (native) + soc usb.type serial-jtag'
- 'Expansion: UART1 TX/RX on GPIO43/44 at the "External QWIIC Socket" are the only pins
  the hardware doc''s pin map marks free; it also lists an External M.2 Socket and an
  external pin header on the PMU rails. io is omitted: the doc does not enumerate the header
  GPIOs'
- 'Buttons: the product page lists "Boot (IO00) + Reset + Power Button"; the PWR button
  is wired to the PMU'
- 'Two hardware revisions: per the hardware doc, V3.1 replaces the magnetometer with
  a QMC6309, adds an onboard BMS and BME280/OLED address-selection resistors over V3.0'
sources:
- field: '*'
  url: https://lilygo.cc/products/t-beam-supreme
  verified: '2026-11-19'
- field: '*'
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: aka
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: soc
  url: https://lilygo.cc/products/t-beam-supreme
  verified: '2026-11-19'
- field: flash_mb
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: psram_mb
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: usb.connector
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: usb.bridge
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/schematic/T-Beam-S3-Supreme/T-Beam-S3-Core.pdf
  verified: '2026-11-19'
- field: usb.bridge
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/schematic/T-Beam-S3-Supreme/T-Beam-S3-Supreme-V3.1.pdf
  verified: '2026-11-19'
- field: usb_serial
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: power
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: display
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: extras
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_hw.md
  verified: '2026-11-19'
- field: notes
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam_supreme/t_beam_supreme_144_hw.md
  verified: '2026-11-19'
---

# T-Beam Supreme

ESP32-S3FN8 LoRa + GNSS board (8 MB flash, 8 MB PSRAM) with an SX1262 or LR1121 radio, an L76K or u-blox M10 GNSS, an SH1106 OLED, QMI8658 IMU, magnetometer, PCF8563 RTC, BME280 sensor, microSD, and an AXP2101 PMU that charges an 18650 cell over USB-C.
