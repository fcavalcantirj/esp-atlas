---
id: soldered-inkplate-10
type: board
brand: soldered
name: Inkplate 10
soc: esp32
flash_mb: 4
psram_mb: 8
form_factor: inkplate
price_tier: expensive
dimensions_mm:
- 224.3
- 163
- 10
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 9.7in 1200x825 greyscale E-Ink
extras:
- e-ink
- sd-card
- rtc
notes:
- '22 uA deep-sleep current'
- RTC has its own battery holder
- Official BOM lists a plain ESP32-WROVER module (4 MB flash, 8 MB PSRAM per Espressif's ESP32-WROVER datasheet), needed for the grayscale framebuffer
sources:
- field: '*'
  url: https://soldered.com/products/inkplate-10
  verified: '2026-08-22'
- field: flash_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Inkplate-10-hardware/master/Schematics,%20Gerber,%20BOM/v1.0/Inkplate%2010%20BOM%20v1.0.xlsx
  verified: '2026-08-24'
- field: psram_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Inkplate-10-hardware/master/Schematics,%20Gerber,%20BOM/v1.0/Inkplate%2010%20BOM%20v1.0.xlsx
  verified: '2026-08-24'
---

# Inkplate 10

An ESP32 board driving a 9.7in 1200x825 greyscale e-paper panel, with a microSD slot, RTC, USB-C, and Li-ion battery charging onboard — Arduino (Adafruit GFX) and MicroPython compatible.
