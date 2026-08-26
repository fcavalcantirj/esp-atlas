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
io:
  gpio_free: 0
notes:
- '25 uA sleep-state current'
- RTC is a PCF85063A with its own battery holder
- Official BOM lists a plain ESP32-WROVER module (4 MB flash, 8 MB PSRAM per Espressif's ESP32-WROVER datasheet), needed for the grayscale framebuffer
- 'io.gpio_free=0 DERIVED, not quoted (SPEC-io-power.md §5.3). Vendor free-GPIO
  page table marks zero native ESP32-WROVER pins FREE: IO12/13/14 go to the microSD
  bus, IO15/34/39 are jumper-gated, IO35 reads V_BAT, IO36 is the wakeup button,
  and TXD/RXD go to the CH340 bridge. Only expander-1 pins P1-3..P1-7 and all of
  expander 2 (21 pins on a separate I2C GPIO-expander chip) are free, excluded
  here as non-native SoC pads. No esp32 reserved_pins subtraction applies since
  the native free set is already empty.'
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
- field: io.gpio_free
  url: https://docs.soldered.com/inkplate/6/hardware/free-gpio/
  verified: '2026-08-26'
---

# Inkplate 6

An ESP32 board driving a 6in 800x600 greyscale e-paper panel, with a microSD reader, RTC, USB-C, and battery-powered/charging operation — Arduino (Adafruit GFX) and MicroPython compatible.
