---
id: esp32-s2-devkitc-1
type: board
brand: espressif
name: ESP32-S2-DevKitC-1
soc: esp32-s2
flash_mb: 8
psram_mb: 2
form_factor: devkit
price_tier: cheap
usb:
  connector: micro-usb
extras:
- rgb-led
notes:
- 'Micro-USB UART-bridge port confirmed; a second, native ESP32-S2 USB OTG interface
  is also present but its physical connector type is not stated in the guide text
  (omitted)'
- Bridge chip model not named in the official user guide (omitted)
- Recommended build is ESP32-S2-DevKitC-1-N8R2 carrying ESP32-S2-SOLO-2, 8 MB flash,
  2 MB PSRAM; other module/flash/PSRAM combinations exist (fixed spec omitted since
  it varies by SKU)
- Dimensions only in separate PDF/DXF files (omitted)
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitc-1/user_guide.html
  verified: '2026-08-22'
---

# ESP32-S2-DevKitC-1

ESP32-S2-SOLO-2 based board with a micro-USB UART bridge plus the chip's native USB OTG interface.
