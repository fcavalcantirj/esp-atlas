---
id: esp32-ethernet-kit
type: board
brand: espressif
name: ESP32-Ethernet-Kit
module: esp32-wrover-e
form_factor: devkit
usb:
  connector: micro-usb
  bridge: ft2232h
extras:
- ethernet
- rj45
- poe-addon
notes:
- 'Board version documented: v1.2'
- 'Two-board kit: the Ethernet board (A) carries the ESP32-WROVER-E module and an
  IP101GRI 10/100 Ethernet PHY (RMII) and can run standalone; an optional PoE board
  (B, IEEE 802.3at, 5 V/1.4 A output) powers board A over the Ethernet cable'
- FT2232H provides a USB-to-JTAG channel (channel A) and a USB-to-serial channel (channel
  B) over a single Micro-USB port
- Onboard Ethernet Link/Activity LEDs, a 4-bit DIP function switch, and BOOT/EN buttons
- GPIO16/GPIO17 are not broken out because they are used internally by the ESP32-WROVER-E
  module's PSRAM
- Flash/PSRAM inherited from the ESP32-WROVER-E module record, not restated here
download_mode:
  mode: auto
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-ethernet-kit/user_guide.html
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-ethernet-kit/user_guide.html
  verified: '2026-08-28'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-ethernet-kit/user_guide.html
  verified: '2026-09-01'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-ethernet-kit/user_guide.html
  verified: '2026-09-01'
---

# ESP32-Ethernet-Kit

ESP32-WROVER-E devkit that bridges Wi-Fi/BLE to wired Ethernet via an onboard IP101GRI PHY and RJ45 jack, with an FT2232H USB-JTAG/UART bridge and an optional Power-over-Ethernet add-on board.
