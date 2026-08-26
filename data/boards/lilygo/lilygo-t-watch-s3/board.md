---
id: lilygo-t-watch-s3
type: board
brand: lilygo
name: T-Watch S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: t-watch
price_tier: medium
extras:
- lora
- rtc
- imu
- microphone
- vibration-motor
io:
  gpio_exposed: 26
  gpio_free: 0
notes:
- 16 MB flash, 8 MB PSRAM
- 'LoRa transceiver: SX1262, 433/868/915MHz'
- 'IMU: BMA423 3-axis accelerometer'
- 'Haptics: DRV2605 driver for ERM/LRA vibration motor'
- 'Power management: AXP2101 PMU'
- Wi-Fi 802.11 b/g/n, Bluetooth BLE v5.0
- 'io.gpio_exposed=26 QUOTED: official "Pins Map" table (LilyGoLib firmware
  repo''s T-Watch-S3 hardware doc) lists every named GPIO with a per-row Free
  column -- {10,11,39,40,16,17,14,48,15,46,3,4,1,8,7,5,9,12,13,18,38,45,21,44,
  47,2} (I2C SDA/SCL 10/11 shared by touch/RTC/PMU/haptic driver).
  io.gpio_free=0 QUOTED: every row is marked "Free: (cross mark)" -- I2C bus
  consumed by touch/RTC/BMA423/AXP2101/DRV2605, LoRa (SX1262) takes 7 pins,
  the ST7789V3 display 5, the PDM mic + PCM amp 5, plus dedicated touch/RTC/
  sensor/charger interrupts and an IR LED -- no header pin is independently
  free; esp32-s3''s soc.reserved_pins subtraction is moot since gpio_free is
  already 0 from the vendor table itself'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-watch-s3
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/master/docs/hardware/lilygo-t-watch-s3.md
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/Xinyuan-LilyGO/LilyGoLib/blob/master/docs/hardware/lilygo-t-watch-s3.md
  verified: '2026-08-26'
---

# T-Watch S3

ESP32-S3 smartwatch board with an SX1262 LoRa transceiver, BMA423 IMU, DRV2605 haptic driver, and an AXP2101 power management unit.
