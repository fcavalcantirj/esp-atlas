---
id: m5cardputer-adv
type: board
brand: m5stack
name: Cardputer-Adv
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: m5-cardputer
dimensions_mm:
- 84.0
- 54.0
- 19.6
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
display: 1.14in 240x135 ST7789V2
extras:
- keyboard
- sd-card
- mic
- speaker
- imu
- headphone-jack
- audio-codec-es8311
io:
  gpio_pins:
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
  - 13
  - 15
  gpio_exposed: 8
  gpio_free: 7
download_mode:
  mode: manual
  steps: Set the side power switch to OFF. Before powering on, press and hold the G0 button while connecting
    the device to a computer via a USB Type-C data cable. Release the button after the device is powered
    on; the device enters download mode.
notes:
- 'Not the original Cardputer (m5cardputer): a Stamp-S3A core module (ESP32-S3FN8) with a 56-key keyboard
  read through a TCA8418 I2C controller (SDA G8, SCL G9, INT G11) instead of a GPIO key matrix, an ES8311
  audio codec with NS4150B amplifier and 8 ohm 1 W speaker, a MEMS microphone, a 3.5 mm audio output
  (inserting it disables the speaker amplifier), a BMI270 6-axis IMU, an infrared emitter (G44), a
  microSD slot, a built-in 1500 mAh battery with an independent power switch (switch it ON to charge),
  and an EXT 2.54-14P expansion bus'
- 'psram_mb=0 DERIVED: the page names the SoC "ESP32-S3FN8"; Espressif''s ESP32-S3 datasheet ordering
  table lists ESP32-S3FN8 with "8 MB (Quad SPI)" in-package flash and no in-package PSRAM ("—")'
- 'usb.bridge native / usb_serial native-usb-serial-jtag: the page flashes over "a USB Type-C data cable";
  the linked Stamp schematic wires the ESP32-S3FN8''s GPIO19/GPIO20 straight to USB_D_N/USB_D_P (no
  USB-UART bridge chip)'
- 'io.gpio_pins / gpio_exposed=8 COUNTED from the page''s PinMap: the HY2.0-4P Grove port (Yellow G2,
  White G1) plus the EXT 2.54-14P pins dedicated to expansion: G3 (RESET), G4 (INT), G6 (BUSY), G5 (CS),
  G13 (UART_TX), G15 (UART_RX). EXT also re-exposes G8/G9 (I2C, shared with the keyboard controller,
  IMU and audio codec) and G40/G14/G39 (SCK/MOSI/MISO, the microSD bus); per SPEC-io-power.md those
  re-exposed onboard buses are usable as their bus but are not counted as free GPIO. Cross-checked against
  the Cardputer-Adv schematic v1.0 (EXT block G3/G4/G5/G6/G13/G15 + G8/G9 + G14/G39/G40). G7 goes only
  to the internal 8-pin FPC, not to a user header.'
- 'io.gpio_free=7 DERIVED: 8 exposed minus esp32-s3 soc.reserved_pins that land on them: strapping
  {0,3,45,46} contains G3, usb_flash_tied {19,20,35,36,37} contains none, so 8 - 1 = 7 (G1, G2, G4, G5,
  G6, G13, G15). No max rail output current is stated on the page, so power_out is omitted.'
- 'The Stamp-S3A adds a power switch for its RGB LED on GPIO38; set GPIO38 high before driving the LED'
getting_started: https://docs.m5stack.com/en/core/Cardputer-Adv
images:
  photo: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1178/Cardputer-Adv_01.webp
platformio_definitions:
- id: m5stack-cardputer
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: ac1db7d8761e5706fb4d1b08106007bfd381c34438a5e4d26a52152b5117b64c
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: psram_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-11-14'
- field: usb
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: usb
  url: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1150/Sch_StampS3_v0.3.3.pdf
  verified: '2026-11-14'
- field: usb_serial
  url: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1150/Sch_StampS3_v0.3.3.pdf
  verified: '2026-11-14'
- field: io.gpio_pins
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: io.gpio_pins
  url: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1178/Sch_M5CardputerAdv_v1.0_2025_06_20_17_19_58.pdf
  verified: '2026-11-14'
- field: io.gpio_exposed
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: io.gpio_free
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: io.gpio_free
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html
  verified: '2026-11-14'
- field: download_mode
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: getting_started
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: images
  url: https://docs.m5stack.com/en/core/Cardputer-Adv
  verified: '2026-11-14'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/m5stack-cardputer.json
  verified: '2026-11-22'
---

# Cardputer-Adv

M5Stack's 84 x 54 mm ESP32-S3 pocket computer built on the Stamp-S3A: a 56-key keyboard on an I2C
controller, 1.14in display, ES8311 audio with speaker and 3.5 mm jack, BMI270 IMU, IR emitter, microSD,
a 1500 mAh battery and an EXT 2.54-14P expansion bus. It is a different board from the original
Cardputer (`m5cardputer`): the keyboard, audio path, IMU and expansion header differ, so firmware
built for one is not automatically compatible with the other.
