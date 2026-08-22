---
id: lilygo-t-beam
type: board
brand: lilygo
name: T-Beam
soc: esp32
form_factor: t-beam
price_tier: medium
usb:
  connector: micro-usb
  bridge: ch9102
power:
  battery_connector: true
  charging: true
display: 0.96in OLED SSD1306
extras:
- lora
- gps
notes:
- 4 MB flash, 8 MB PSRAM
- 'LoRa transceiver: SX1278 (433MHz) or SX1276 (868/915/923MHz), region-dependent SKU'
- 'GPS: NEO-6M module with onboard RTC crystal'
- 'Power management: AXP2101 PMU; USB Micro can power/charge an 18650 cell held in the onboard holder (battery not included)'
- Wi-Fi + Bluetooth 4.2; 3 buttons (Power/IO38/Reset)
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-beam
  verified: '2026-08-22'
---

# T-Beam

ESP32 board with an SX1276/SX1278 LoRa transceiver and a NEO-6M GPS module, a 0.96in SSD1306 OLED display, and an AXP2101 PMU that charges an 18650 cell over Micro-USB.
