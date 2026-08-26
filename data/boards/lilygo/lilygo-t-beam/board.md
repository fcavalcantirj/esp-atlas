---
id: lilygo-t-beam
type: board
brand: lilygo
name: T-Beam
soc: esp32
flash_mb: 4
psram_mb: 8
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
io:
  gpio_exposed: 13
  gpio_free: 0
notes:
- 4 MB flash, 8 MB PSRAM
- 'LoRa transceiver: SX1278 (433MHz) or SX1276 (868/915/923MHz), region-dependent SKU'
- 'GPS: NEO-6M module with onboard RTC crystal'
- 'Power management: AXP2101 PMU; USB Micro can power/charge an 18650 cell held in the onboard holder (battery not included)'
- Wi-Fi + Bluetooth 4.2; 3 buttons (Power/IO38/Reset)
- 'io.gpio_exposed=13 QUOTED: official "Pins Map" table lists every named GPIO
  with a per-row Free column -- {21,22,12,34,5,19,27,23,33,32,18,38,35} (SDA/SCL
  21/22 shared by I2C bus, OLED, and PMU). io.gpio_free=0 QUOTED: every row in
  that table is marked "Free: (cross mark)" -- SDA/SCL consumed by the shared
  I2C bus (OLED SSD1306 + AXP2101 PMU), GPIO12/34 by GNSS, GPIO5/19/27/23/33/32/18
  by the LoRa radio, GPIO38 by Button1, GPIO35 by the PMU IRQ line -- so no
  header pin is independently free; esp32''s soc.reserved_pins subtraction is
  moot since gpio_free is already 0 from the vendor table itself'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-beam
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam/t_beam_hw.md
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series/blob/master/docs/en/t_beam/t_beam_hw.md
  verified: '2026-08-26'
---

# T-Beam

ESP32 board with an SX1276/SX1278 LoRa transceiver and a NEO-6M GPS module, a 0.96in SSD1306 OLED display, and an AXP2101 PMU that charges an 18650 cell over Micro-USB.
