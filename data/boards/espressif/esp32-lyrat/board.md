---
id: esp32-lyrat
type: board
brand: espressif
name: ESP32-LyraT
aka:
- ESP32-LyraT V4.3
module: esp32-wrover-e
form_factor: audio-dev
usb:
  connector: micro-usb
power:
  battery_connector: true
  charging: true
extras:
- audio-codec-es8388
- mic
- sd-card
- speaker-out
- headphone-jack
- aux-in
notes:
- 'Version documented: V4.3, the current revision in the ESP-ADF hardware-reference
  docs. Earlier V4/V4.2 hardware revisions exist but are not separately catalogued
  here.'
- 'ESP32-LyraTD-MSC is a distinct audio devkit (dual-board smart-speaker/mic-array
  design around a MicroSemi/Ambiq DSP chip, not just an ESP32-LyraT variant) with
  its own official guide -- not mapped this pass, left for future coverage'
- ES8388 audio codec drives 2x onboard microphones, stereo speaker outputs (4 ohm
  / 3 W recommended), a 3.5 mm headphone jack, and a 3.5 mm aux-in socket
- Four touch buttons (Play, Sel, Vol+, Vol-) and two push buttons (Rec, Mode)
- AP5056 single-cell Li-ion battery charger, charges over the Micro-USB port
- MicroSD card slot (SPI/1-bit/4-bit modes); shares the JTAG header and cannot be
  used while JTAG is in operation
- USB-UART bridge chip not named by part number on the hardware-reference page
- Flash/PSRAM (4 MB flash, 8 MB PSRAM per this page) match the ESP32-WROVER-E module
  record defaults and are not restated here
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-adf/en/latest/design-guide/dev-boards/board-esp32-lyrat-v4.3.html
  verified: '2026-08-28'
---

# ESP32-LyraT

ESP32-WROVER-E audio devkit built around an ES8388 codec: dual mic input, stereo speaker/headphone output, MicroSD, Li-ion battery charging, and touch/push buttons for Wi-Fi/BLE audio applications.
