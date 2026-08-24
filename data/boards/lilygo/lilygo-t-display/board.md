---
id: lilygo-t-display
type: board
brand: lilygo
name: T-Display
soc: esp32
psram_mb: 0
form_factor: t-display
price_tier: medium
usb:
  bridge: ch9102
display: 1.14in 135x240 ST7789 SPI IPS
notes:
- 4 MB or 16 MB flash options (board-level default/most-common SKU not confirmed in vendor docs, so flash_mb is left unset)
- Onboard battery power detection circuit
- Wi-Fi 802.11 b/g/n, Bluetooth v4.2+BLE
- LilyGO's official Arduino IDE setup guide instructs users to select "Disable" for PSRAM, confirming this board has none
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-display
  verified: '2026-08-22'
- field: psram_mb
  url: https://github.com/Xinyuan-LilyGO/TTGO-T-Display/blob/master/README.MD
  verified: '2026-08-24'
---

# T-Display

Original ESP32 dev board with a 1.14in 135x240 ST7789 SPI IPS display and a CH9102 USB-serial bridge.
