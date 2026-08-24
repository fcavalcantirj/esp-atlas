---
id: esp32-pico-kit
type: board
brand: espressif
name: ESP32-PICO-KIT
soc: esp32
flash_mb: 4
psram_mb: 0
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 52
- 20.3
- 10
usb:
  connector: micro-usb
notes:
- Micro-USB UART-bridge port; bridge chip is CP2102 on v4 (up to 1 Mbps) or CP2102N
  on v4.1 (up to 3 Mbps) — version-dependent, so usb.bridge left unset
- Built around the ESP32-PICO-D4 SiP (complete ESP32 system including 4 MB flash);
  no PSRAM
- Single red 5V Power-On LED
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-pico-kit/user_guide.html
  verified: '2026-08-22'
---

# ESP32-PICO-KIT

Small ESP32-PICO-D4 SiP board (52 x 20.3 x 10 mm) with a single micro-USB UART-bridge port.
