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
io:
  gpio_free: 1
notes:
- '22 uA deep-sleep current'
- RTC has its own battery holder
- Official BOM lists a plain ESP32-WROVER module (4 MB flash, 8 MB PSRAM per Espressif's ESP32-WROVER datasheet), needed for the grayscale framebuffer
- 'io.gpio_free=1 DERIVED, not quoted (SPEC-io-power.md §5.3). Vendor free-GPIO
  page states the Inkplate 10 pins "not connected to any external component": IO26
  (native ESP32), plus GPIO expander 1 P1-3..P1-7 and expander 2 P0-0..P1-7 (21
  more I/O on the separate PCAL6416A I2C expander, excluded here -- not native SoC
  GPIO pads). Of the native set {IO26}, none fall in esp32''s reserved_pins (strapping
  {0,2,5,12,15}, input_only {34,35,36,39}, usb_flash_tied {6,7,8,9,10,11}), so 1
  - 0 = 1. Math not vendor-stated; verify before treating as exact.'
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
- field: io.gpio_free
  url: https://docs.soldered.com/inkplate/10/hardware/free-gpio/
  verified: '2026-08-26'
---

# Inkplate 10

An ESP32 board driving a 9.7in 1200x825 greyscale e-paper panel, with a microSD slot, RTC, USB-C, and Li-ion battery charging onboard — Arduino (Adafruit GFX) and MicroPython compatible.
