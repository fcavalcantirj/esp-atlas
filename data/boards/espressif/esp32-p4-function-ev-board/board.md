---
id: esp32-p4-function-ev-board
type: board
brand: espressif
name: ESP32-P4-Function-EV-Board
aka:
- esp32-p4-evboard
soc: esp32-p4
flash_mb: 16
form_factor: devkit
usb:
  connector: usb-c
  bridge: native
extras:
- ethernet
- rj45
- sd-card
- mic
- speaker-out
- audio-codec-es8311
io:
  gpio_pins:
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
  - 20
  - 21
  - 22
  - 23
  - 26
  - 27
  - 32
  - 33
  - 36
  - 37
  - 38
  - 46
  - 47
  - 48
  - 53
  - 54
notes:
- 'Board version documented: v1.5.2. Espressif now lists this board under EOL (End
  of Life) Boards; the user guide points ESP32-P4X-Function-EV-Board (chip revision
  v3.x) users to that board''s own guide -- a separate product, not this record'
- 'Wireless comes from an onboard ESP32-C6-MINI-1 module (2.4 GHz Wi-Fi 6 & Bluetooth
  5 LE), with its own programming connector for ESP-Prog or other UART tools'
- 'Three USB Type-C ports plus one USB Type-A: USB Serial/JTAG port (recommended for
  flashing and debugging), USB Full-speed port, and a USB 2.0 Type-C port wired to the
  P4''s USB 2.0 OTG High-Speed interface (device role); the USB 2.0 Type-A port shares
  that High-Speed interface in host role (up to 500 mA via a TPS2051C switch) and the
  two cannot be used simultaneously'
- 'Onboard: RJ45 10/100 Mbps Ethernet via an Ethernet PHY on the P4 EMAC RMII interface,
  MicroSD slot (4-bit mode), microphone, ES8311 audio codec, NS4150B 3 W class-D amplifier
  driving a speaker output port (4 ohm, 3 W, 2.00 mm pitch), MIPI CSI and MIPI DSI
  15-pin 1.0 mm FPC connectors, power switch, BOOT and Reset buttons'
- 'Optional accessories (not on the board itself): 7-inch 1024 x 600 capacitive touch
  LCD with adapter board, and a 2MP MIPI CSI camera with adapter board'
- PSRAM size is not stated for this board in its user guide or schematic, so psram_mb
  is omitted rather than guessed
- 'J1 header pins NC(0), NC(1) and NC(45) are excluded from gpio_pins: GPIO0/GPIO1
  need the 32.768 kHz XTAL function disabled (move R61/R59 to R199/R197) and GPIO45
  needs SD_PWRn disabled (move R231 to R100)'
- 'The LCD adapter board uses J1 GPIO27 (RST_LCD) and GPIO26 (PWM) by default'
- 'Hardware v1.4 (older revision of the same board) used a CP2102N USB-to-UART port
  with automatic download instead of the native USB Serial/JTAG port, had no Full-speed
  USB OTG Type-C port, and also broke out IO24/IO25 on the header'
download_mode:
  mode: manual
  steps: Press the Reset Button while holding down the Boot Button to reset ESP32-P4
    and enter firmware download mode
  note: Firmware is downloaded via the USB Serial/JTAG Port, the port the user guide
    recommends for flashing and debugging
usb_serial: native-usb-serial-jtag
getting_started: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
images:
  photo: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/_images/esp32-p4-function-ev-board-isometric_v1.5.2.png
platformio_definitions:
- id: esp32-p4-evboard
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 3ea208ff313739a724e032cdccc0a9be44ec760e19f301b3fa319079f9ca6575
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: flash_mb
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: io.gpio_pins
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: io.gpio_pins
  url: https://dl.espressif.com/dl/schematics/esp32-p4-function-ev-board-schematics_v1.52.pdf
  verified: '2026-11-14'
- field: extras
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: download_mode
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: usb_serial
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: getting_started
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: images
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide.html
  verified: '2026-11-14'
- field: notes
  url: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-function-ev-board/user_guide_v1.4.html
  verified: '2026-11-14'
- field: notes
  url: https://dl.espressif.com/dl/schematics/esp32-p4-function-ev-board-schematics_v1.52.pdf
  verified: '2026-11-14'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/esp32-p4-evboard.json
  verified: '2026-11-14'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/esp32-p4-evboard.json
  verified: '2026-11-22'
---

# ESP32-P4-Function-EV-Board

Espressif's (now end-of-life) ESP32-P4 multimedia devkit: an ESP32-C6-MINI-1 module provides Wi-Fi 6/BLE, with 16 MB SPI flash, MIPI CSI/DSI connectors, 10/100 Ethernet, MicroSD, an ES8311 audio path and native USB Serial/JTAG flashing. Not to be confused with its successor, the ESP32-P4X-Function-EV-Board.
