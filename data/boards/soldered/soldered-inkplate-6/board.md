---
id: soldered-inkplate-6
type: board
brand: soldered
name: Inkplate 6
soc: esp32
flash_mb: 4
psram_mb: 8
form_factor: inkplate
price_tier: expensive
dimensions_mm:
- 144.5
- 107.8
- 10
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 6in 800x600 greyscale E-Ink
extras:
- e-ink
- sd-card
- rtc
notes:
- '25 uA sleep-state current'
- RTC is a PCF85063A with its own battery holder
- Official BOM lists a plain ESP32-WROVER module (4 MB flash, 8 MB PSRAM per Espressif's ESP32-WROVER datasheet), needed for the grayscale framebuffer
sources:
- field: '*'
  url: https://soldered.com/products/inkplate-6-6-e-paper-board
  verified: '2026-08-22'
- field: flash_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Inkplate-6-hardware/master/Schematics,%20Gerber,%20BOM/v1.0/Inkplate6%20BOM.xlsx
  verified: '2026-08-24'
- field: psram_mb
  url: https://raw.githubusercontent.com/SolderedElectronics/Inkplate-6-hardware/master/Schematics,%20Gerber,%20BOM/v1.0/Inkplate6%20BOM.xlsx
  verified: '2026-08-24'
---

# Inkplate 6

An ESP32 board driving a 6in 800x600 greyscale e-paper panel, with a microSD reader, RTC, USB-C, and battery-powered/charging operation — Arduino (Adafruit GFX) and MicroPython compatible.
