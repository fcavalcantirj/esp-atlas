---
id: elecrow-crowpanel-esp32-s3-579-epaper
type: board
brand: elecrow
name: CrowPanel ESP32-S3 5.79" E-Paper HMI Display
aka:
- elecrow_crowpanel_579
- CrowPanel 5.79
module: esp32-s3-wroom-1
flash_mb: 8
psram_mb: 8
display: 5.79in 272x792 e-paper SSD1683 x2 (SPI)
power:
  battery_connector: true
extras:
- sd-card
notes:
- 'Product page: module "ESP32-S3-WROOM-1-N8R8", 240 MHz, "8 MB Flash, 8 MB PSRAM"'
- 'Display: 5.79-inch e-paper, "272(H)*792(L) Pixel", driver "SSD1683 x2", "3-/4-wire
  SPI, default 4-wire SPI"; active area "47.74 x 139.00 mm (H x L)"'
- '"BAT interface (SH1.0-2P connector)" supporting "2.2~3.7V"; charging circuit not
  detailed on the page (charging omitted); "TF Card Slot x1", "UART0 x1", "GPIO x1";
  Rotary Switch, Menu, Back, Reset and BOOT buttons'
- USB connector type is not stated (page lists "1x USB Cable" only; omitted)
- aka "elecrow_crowpanel_579" is the device token draftling uses for its release binaries
getting_started: https://www.elecrow.com/wiki/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display.html
images:
  pinout: https://www.elecrow.com/wiki/assets/images/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display/ESP32-EPAPER-5.79inch-pinout.webp
sources:
- field: '*'
  url: https://www.elecrow.com/crowpanel-esp32-5-79-e-paper-hmi-display-with-272-792-resolution-black-white-color-driven-by-spi-interface.html
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
- field: getting_started
  url: https://www.elecrow.com/wiki/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display.html
  verified: '2026-09-11'
- field: images
  url: https://www.elecrow.com/wiki/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display.html
  verified: '2026-09-11'
---

# Elecrow CrowPanel ESP32-S3 5.79" E-Paper HMI Display

A 5.79-inch 272x792 e-paper HMI board on an ESP32-S3-WROOM-1-N8R8 (8 MB flash, 8 MB PSRAM) with a battery connector, TF-card slot and a rotary switch.
