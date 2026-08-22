---
id: soldered-inkplate-6
type: board
brand: soldered
name: Inkplate 6
soc: esp32
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
sources:
- field: '*'
  url: https://soldered.com/products/inkplate-6-6-e-paper-board
  verified: '2026-08-22'
---

# Inkplate 6

An ESP32 board driving a 6in 800x600 greyscale e-paper panel, with a microSD reader, RTC, USB-C, and battery-powered/charging operation — Arduino (Adafruit GFX) and MicroPython compatible.
