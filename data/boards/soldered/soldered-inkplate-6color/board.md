---
id: soldered-inkplate-6color
type: board
brand: soldered
name: Inkplate 6COLOR
soc: esp32
flash_mb: 4
psram_mb: 8
form_factor: inkplate
price_tier: expensive
dimensions_mm:
- 131.5
- 105.5
- 10
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 5.85in 600x448 7-color E-Ink
extras:
- e-ink
- sd-card
- rtc
notes:
- 7-color panel (black, white, red, yellow, blue, green, orange) with dithering
- Official BOM lists a plain ESP32-WROVER module (4 MB flash, 8 MB PSRAM per Espressif's ESP32-WROVER datasheet), needed for the color framebuffer
sources:
- field: '*'
  url: https://soldered.com/products/inkplate-6color-e-paper-display
  verified: '2026-08-22'
- field: flash_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Soldered-Inkplate-6-COLOR-hardware-design/main/OUTPUTS/V1.2.1/Soldered%20Inkplate%206COLOR%20BOM.csv
  verified: '2026-08-24'
- field: psram_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Soldered-Inkplate-6-COLOR-hardware-design/main/OUTPUTS/V1.2.1/Soldered%20Inkplate%206COLOR%20BOM.csv
  verified: '2026-08-24'
---

# Inkplate 6COLOR

An ESP32 board driving a 5.85in 7-color e-paper panel, with a microSD reader, RTC, USB-C, and onboard Li-ion charging — Arduino (Adafruit GFX) and MicroPython compatible.
