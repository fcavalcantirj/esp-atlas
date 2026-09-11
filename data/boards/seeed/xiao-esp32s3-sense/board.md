---
id: xiao-esp32s3-sense
type: board
brand: seeed
name: Seeed Studio XIAO ESP32S3 Sense
soc: esp32-s3
flash_mb: 8
psram_mb: 8
form_factor: xiao
price_tier: cheap
dimensions_mm:
- 21
- 17.8
- 15
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- camera
- mic
- sd-card
- external-antenna-ipex
io:
  gpio_exposed: 11
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 700
notes:
- '8 MB flash + 8 MB on-chip PSRAM: Specifications table (Sense column) Memory row states
  "On-chip 8MB PSRAM & 8MB Flash"'
- 'Sense = XIAO ESP32-S3 + detachable camera + digital (PDM) mic + microSD. Vendor:
  "XIAO ESP32-S3 Sense integrates camera sensor, digital microphone and SD card supporting."'
- 'camera QUOTED: Specifications table (Sense) Built-in Sensors row states "1x OV3660
  camera sensor". Vendor note: "The OV2640 camera has been discontinued, and the subsequent
  XIAO ESP32-S3 Sense uses the OV3660 camera model." Detachable module: "Detachable
  OV2640 camera sensor for 1600x1200 resolution and OV3660 camera sensor for 2048x1536
  compatible with OV5640 camera sensor".'
- 'mic QUOTED: Built-in Sensors row states "1x Digital Microphone"; Pin Map "Digital
  microphone_CLK GPIO42 PDM clock pin for MIC", "Digital microphone_DATA GPIO41 PDM
  data pin for MIC" (PDM).'
- 'sd-card QUOTED: Specifications table (Sense) Memory row states "Onboard SD Card Slot,
  supporting 32GB FAT"'
- 'dimensions_mm QUOTED: Specifications table (Sense) Dimensions row states "21 x 17.8
  x 15mm (with expansion board)". (Bare board footprint is 21 x 17.8mm; the 15 mm height
  is with the Sense expansion board fitted.)'
- 'usb.connector=usb-c: Specifications table Power(Typ.) row states "Input voltage (Type-C):
  5V"'
- U.FL external antenna (Pin Map "U.FL-R-SMT1 ... UFL antenna")
- 'onboard LiPo charging + charge LED: vendor states "Lithium battery charge management
  capability"; Specifications table lists "1x Charge LED"'
- 'io.gpio_exposed=11 QUOTED: vendor Specifications table (Sense column) states "11x
  GPIOs (PWM)"'
- 'io.gpio_free OMITTED: not vendor-stated and not cleanly derivable for the Sense. The
  expansion board hard-consumes several of the D0-D10 pads -- the onboard microSD uses
  the SPI bus on D8/D9/D10 (Pin Map quoted: "Onboard SD Card_SCK GPIO7", "Onboard SD
  Card_MISO GPIO8", "Onboard SD Card Slot_MOSI GPIO9" = D8/D9/D10; plus "Onboard SD
  Card__CS GPIO21") and the camera/mic attach via the "1x B2B Connector (with 2 additional
  GPIOs)" -- so the free-pad count depends on whether the expansion board is fitted.
  Left out rather than guess (SPEC-io-power.md §5.3, when in doubt omit).'
- 'io.power_out QUOTED: vendor "Power Pins" section states "3V3 - This is the regulated
  output from the onboard regulator. You can draw 700mA"'
- 'aka OMITTED: no distinct arduino-esp32 / pioarduino board id for the Sense (boards.txt
  lists XIAO_ESP32S3 / XIAO_ESP32S3_Plus but no Sense; pioarduino has seeed_xiao_esp32s3.json
  but no sense json). The Sense is flashed as the plain XIAO ESP32-S3 target.'
sources:
- field: '*'
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-09-11'
- field: io.gpio_exposed
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-09-11'
- field: io.power_out
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-09-11'
---

# Seeed Studio XIAO ESP32S3 Sense

The camera/mic/microSD "Sense" variant of the XIAO ESP32-S3: bare-S3R8 board (8 MB flash + 8 MB PSRAM, USB-C, LiPo charging, U.FL antenna) plus a detachable expansion board carrying an OV3660/OV2640 camera, a PDM digital microphone, and a microSD slot (32 GB FAT).
