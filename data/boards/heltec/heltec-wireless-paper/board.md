---
id: heltec-wireless-paper
type: board
brand: heltec
name: Wireless Paper
soc: esp32-s3
form_factor: heltec
price_tier: cheap
dimensions_mm:
- 88
- 88
- 25
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 2.13in 122x250 E-Ink
extras:
- lora
- e-ink
notes:
- ESP32-S3FN8
- SX1262 LoRa transceiver, user-selectable 433/470-510/863-870/902-928 MHz bands
- E-Ink image persists ~180 days without power; drag-and-drop BMP refresh
sources:
- field: '*'
  url: https://heltec.org/project/wireless-paper/
  verified: '2026-08-22'
---

# Wireless Paper

ESP32-S3FN8 + SX1262 LoRa dev board with a 2.13in E-Ink display, USB-C, and lithium battery charging — built for ultra-low-power always-on displays.
