---
id: lolin-d32-pro
type: board
brand: lolin
name: LOLIN D32 Pro
soc: esp32
psram_mb: 4
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 65
- 25.4
usb:
  bridge: ch340
power:
  battery_connector: true
  charging: true
extras:
- sd-card
io:
  gpio_exposed: 22
  gpio_free: 15
notes:
- ESP32 Wi-Fi + Bluetooth chip; 16 MB or 4 MB flash (variant-dependent), 4 MB PSRAM
- TF (Micro SD) card slot, SPI mode
- Onboard LOLIN I2C port and LOLIN TFT port headers
- Lithium battery interface, PH-2.0 2-pin connector, 500 mA max charging current,
  supports 3.7 V LiPo
- Built-in LED on GPIO5
- Physical USB connector shape not stated on the official page (omitted)
- 'Weight: 7.5 g'
- 'io.gpio_exposed=22 QUOTED: vendor page Technical specs table states "Digital
  I/O Pins | 22". The 500 mA figure on this page is LiPo charging current, not
  a GPIO/rail output rating, so power_out is omitted'
- 'io.gpio_free=15 DERIVED: the vendor''s own labeled pinout diagram (d32_pro_v2.0.0
  silkscreen photo) enumerates 23 header GPIO pads (VP/36, VN/39, 34, 32, 33, 25,
  26, 27, 14, 12, 13, 23, 22, GPIO1/TX, GPIO3/RX, 21, 19, 18, 5, 4, 0, 2, 15) --
  2 fewer than the sibling D32''s 25, because GPIO16/17 are marked NC here (consumed
  internally by the onboard WROVER module''s 4 MB PSRAM interface, confirmed by
  psram_mb=4 and absent from D32''s own PSRAM-less pinout). This 23-pad count does
  not reconcile with the vendor''s own "22" spec-table figure, which is identical
  wording to the plain D32''s page and looks copy-pasted rather than Pro-specific,
  so the enumerated 23 is used as the derivation base. Of esp32''s soc.reserved_pins,
  strapping 0/2/5/12/15 are all exposed (5, GPIO5 also BUILTIN_LED per the official
  arduino-esp32 d32_pro/pins_arduino.h); input_only 34/36/39 are exposed (3);
  usb_flash_tied 6/7/8 are not on the header. The onboard TF (microSD) card''s
  CS (GPIO4 per that same pins_arduino.h) and the FPC TFT-port pins (14/32/33/27)
  share their header pads rather than exclusively consuming them, so neither is
  separately subtracted (same treatment as the adafruit-metro-esp32-s3 shared-bus
  precedent) -- 23 - 5 - 3 = 15'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/d32/d32_pro.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/d32/d32_pro.html
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://www.wemos.cc/en/latest/_images/d32_pro_v2.0.0_1_16x16.jpg
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/espressif/arduino-esp32/blob/master/variants/d32_pro/pins_arduino.h
  verified: '2026-08-26'
---

# LOLIN D32 Pro

ESP32 devkit with 16 MB flash (4 MB variant), 4 MB PSRAM, Micro SD slot, LOLIN I2C/TFT ports, LiPo battery/charging interface, CH340 USB-UART bridge.
