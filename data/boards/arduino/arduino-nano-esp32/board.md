---
id: arduino-nano-esp32
type: board
brand: arduino
name: Nano ESP32
aka:
- Arduino Nano ESP32
- ABX00083
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: nano
dimensions_mm:
- 43.18
- 17.78
usb:
  connector: usb-c
  bridge: native
extras:
- rgb-led
io:
  gpio_pins:
  - 0
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
  - 9
  - 10
  - 11
  - 12
  - 13
  - 14
  - 17
  - 18
  - 21
  - 38
  - 43
  - 44
  - 46
  - 47
  - 48
notes:
- The ESP32-S3 sits inside a u-blox NORA-W106-10B module (not an Espressif module);
  the record references the soc directly because the catalog has no NORA-W106 module
  record. The 8 MB octal-SPI PSRAM is embedded in the NORA-W106-10B; the 16 MB flash
  is an external GD25B128EWIGR (U3) on the board.
- Arduino's datasheet (SKU ABX00083) describes the board "with and without headers".
- 'io.gpio_pins is the raw header-exposed set from Arduino''s full pinout (SKU ABX00083):
  D0-D13 = GPIO44, 43, 5, 6, 7, 8, 9, 10, 17, 18, 21, 38, 47, 48; A0-A7 = GPIO1, 2,
  3, 4, 11, 12, 13, 14; B0 = GPIO46 and B1 = GPIO0. D13 (GPIO48) is LED_BUILTIN.'
- The RGB LED is red GPIO46, green GPIO0, blue GPIO45; the red (GPIO46) and green (GPIO0)
  LED pins are also connected to the B0 and B1 header pins. Arduino notes some boards
  from the first limited production batch have an RGB LED with the green and blue pins
  inverted (full pinout, page 3).
- D1/TX0 has a 499 ohm series resistor, which limits the current that pin can drive
  (Arduino full pinout, page 3).
- 'Power: VIN accepts 6-21 V, USB-C 4.8-5.5 V; logic is 3.3 V and there is no 5 V
  pin -- VBUS carries 5 V only when the board is powered over USB (datasheet §3, §11).'
- 'Board recovery: Arduino''s bootloader is entered by double-tapping the reset button
  right after power-up (datasheet §14.5).'
getting_started: https://docs.arduino.cc/hardware/nano-esp32/
sources:
- field: '*'
  url: https://docs.arduino.cc/hardware/nano-esp32/
  verified: '2026-11-10'
- field: flash_mb
  url: https://docs.arduino.cc/resources/datasheets/ABX00083-datasheet.pdf
  verified: '2026-11-10'
- field: psram_mb
  url: https://docs.arduino.cc/resources/datasheets/ABX00083-datasheet.pdf
  verified: '2026-11-10'
- field: form_factor
  url: https://docs.arduino.cc/resources/datasheets/ABX00083-datasheet.pdf
  verified: '2026-11-10'
- field: dimensions_mm
  url: https://docs.arduino.cc/resources/datasheets/ABX00083-datasheet.pdf
  verified: '2026-11-10'
- field: usb
  url: https://docs.arduino.cc/resources/pinouts/ABX00083-full-pinout.pdf
  verified: '2026-11-10'
- field: extras
  url: https://docs.arduino.cc/resources/pinouts/ABX00083-full-pinout.pdf
  verified: '2026-11-10'
- field: io.gpio_pins
  url: https://docs.arduino.cc/resources/pinouts/ABX00083-full-pinout.pdf
  verified: '2026-11-10'
- field: getting_started
  url: https://docs.arduino.cc/hardware/nano-esp32/
  verified: '2026-11-10'
---

# Nano ESP32

Arduino's Nano-form-factor board built on the u-blox NORA-W106-10B (ESP32-S3), with
16 MB of external flash, 8 MB of PSRAM in the module, an RGB LED and a USB-C connector
wired to the ESP32-S3's native USB (GPIO19/GPIO20).
