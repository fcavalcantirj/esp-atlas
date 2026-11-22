---
id: heltec-wifi-lora-32-v4
type: board
brand: heltec
name: WiFi LoRa 32 (V4)
aka:
- HTIT-WB32LAF
soc: esp32-s3
flash_mb: 16
psram_mb: 2
form_factor: heltec
dimensions_mm:
- 51.7
- 25.4
- 10.7
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
display: 0.96in 128x64 OLED SSD1315
extras:
- lora
io:
  gpio_exposed: 32
  gpio_pins:
  - 0
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 15
  - 16
  - 17
  - 18
  - 19
  - 20
  - 21
  - 26
  - 33
  - 34
  - 35
  - 36
  - 37
  - 38
  - 39
  - 40
  - 41
  - 42
  - 43
  - 44
  - 45
  - 46
  - 47
  - 48
download_mode:
  mode: manual
  steps: Connect the USB-C cable, then hold down the PRG button, press the RST button
    once, and release the PRG button
notes:
- 'ESP32-S3R2 with external flash: the datasheet reads "Base on ESP32-S3R2 & SX-1262,
  supports Wi-Fi b/g/n, BLE, and LoRa communication." and "2MB PSRAM and 16MB external
  Flash"'
- 'Distinct from the WiFi LoRa 32 V4-R8 sibling: the product page reads "The WiFi LoRa
  32 now comes with the latest ESP32-S3R8 version. They use different firmware versions."
  The V4-R8 (ESP32-S3R8, 8 MB PSRAM) moves Vext_Ctrl, VGNSS_Ctrl and LED to other GPIOs
  and is a separate record; this one is the ESP32-S3R2 / 2 MB PSRAM board'
- 'usb.bridge=native DERIVED: Heltec''s V3-vs-V4 comparison lists the USB to Serial
  Chip as CP2102 on V3 and "Removed CP2102" on V4, and the V4 datasheet routes the
  ESP32-S3''s own USB pins to the connector ("GPIO19,U1RTS,ADC2_CH8, USB_D-" and "GPIO20,U1CTS,ADC2_CH9,
  USB_D+"); usb_serial derived from usb.bridge (native) + soc usb.type serial-jtag'
- 'power: the datasheet lists a "SH1.25-2P lithium battery interface" and a Charging
  mode (USB@5V, 500 mA typical) in its power consumption table; it also adds a solar
  input ("Added SH1.25-2P solar panel interface.") and a GNSS connector ("Added SH1.25-8Pin
  GNSS interface.") -- the GNSS receiver itself is not on the board'
- 'io.gpio_exposed=32 DERIVED from the datasheet pin tables and Heltec''s V4 pin map:
  Header J2 GPIO {44,43,0,36,35,34,33,47,48,26,21,20,19} (13), Header J3 GPIO {37,46,45,42,41,40,39,38,1,2,3,4,5,6,7}
  (15) and the four "Additional Pin" pads GPIO {18,17,16,15} on the two 2-pin headers
  ("2*18*2.54 Header Pins, 2*2*2.54 Header Pins") = 32. The SX1262 SPI/control lines
  (GPIO8-14) are wired onboard and never reach a header. io.gpio_free is omitted: several
  exposed pins double as onboard control lines (OLED RST/SDA/SCL, Vext_Ctrl, ADC_Ctrl,
  LED, GNSS, LoRa FEM) that differ between hardware revisions'
- 'Two hardware revisions share this name: Heltec''s guide says to select USE_GC1109_PA
  for V4.2 and USE_KCT8103L_PA for V4.3 in the Arduino LoRa FEM menu'
- 'LoRa: the high-power version (HTIT-WB32LAF, 863-928 MHz) transmits up to 28 +/- 1 dBm
  per the datasheet; the product page also lists a low-power version (433-510 MHz)'
- 'The product page offers the board with the OLED or with no display; display describes
  the default OLED version'
getting_started: https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v4/
images:
  pinout: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/Pinmap/V4_pinmap.png
platformio_definitions:
- id: heltec_wifi_lora_32_V4
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: da570fbdb4596a1d606906d97bd571a6758dd27209772981dfc28ef66acf08f8
sources:
- field: '*'
  url: https://heltec.org/project/wifi-lora-32-v4/
  verified: '2026-11-18'
- field: '*'
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: aka
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: soc
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: flash_mb
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: psram_mb
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: form_factor
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: dimensions_mm
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: usb.connector
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: usb.bridge
  url: https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v4/
  verified: '2026-11-18'
- field: usb.bridge
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: usb_serial
  url: https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v4/
  verified: '2026-11-18'
- field: power
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: display
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: extras
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/Pinmap/V4_pinmap.png
  verified: '2026-11-18'
- field: io.gpio_pins
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/datasheet/WiFi_LoRa_32_V4.3.1_Datasheet.pdf
  verified: '2026-11-18'
- field: io.gpio_pins
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/Pinmap/V4_pinmap.png
  verified: '2026-11-18'
- field: download_mode
  url: https://heltec.org/project/wifi-lora-32-v4/
  verified: '2026-11-18'
- field: getting_started
  url: https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v4/
  verified: '2026-11-18'
- field: images.pinout
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V4/Pinmap/V4_pinmap.png
  verified: '2026-11-18'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/heltec_wifi_lora_32_V4.json
  verified: '2026-11-22'
---

# WiFi LoRa 32 (V4)

ESP32-S3R2 (2 MB PSRAM) + 16 MB external flash + SX1262 LoRa board with a 0.96in OLED, native USB-C, lithium battery charging, a solar input and a GNSS connector. Form factor and pinout compatible with the WiFi LoRa 32 V3; Meshtastic, MeshCore and LoRaWAN compatible.
