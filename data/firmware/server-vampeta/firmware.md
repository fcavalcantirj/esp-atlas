---
id: server-vampeta
type: firmware
name: Server vampeta
url: https://github.com/elguesabal/Server-vampeta
category: home
maintainer: elguesabal
capabilities:
- on-device-web-ui
- wifi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/elguesabal/Server-vampeta
  verified: '2026-08-27'
---

This repository contains the code to turn the M5Stack Cardputer into a WiFi hotspot, providing a web interface stored on the SD card and a back-end API for interaction.

The project creates a WiFi server on the Cardputer, allowing connected devices to access:

Front-end: HTML pages stored in the Front-end folder on the SD card.

Back-end: API developed in C++ stored in the Back-end folder on the SD card.



Este repositório contém o código para transformar o M5Stack Cardputer em um ponto de acesso WiFi, fornecendo uma interface web armazenada no cartão SD e uma API back-end para interação.

O projeto cria um servidor WiFi no Cardputer, permitindo que dispositivos conectados acessem:

Front-end: Páginas HTML armazenadas na pasta Front-end do cartão SD.
Back-end: API desenvolvida em C++ armazenada na pasta Back-end do cartão SD.
