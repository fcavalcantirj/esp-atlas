# M5Cardputer_WebRadio

M5Cardputer_WebRadio based on the libraries:

M5Unified : https://github.com/m5stack/M5Unified 

The list of radios is stored in a text file (station_list.txt) at the root of the SD card
Ex:
Nome da Radio01,http://Link da Radio/stream01
Nome da Radio02,http://Link da Radio/stream02
- Press R key to reset the connection with the server if the radio freezes or does not start
- Press M key to toggle mute
- Press F key to toggle FFT
- Ability to play AAC or MP3 radios
- Saves WiFi settings in memory

- Example station_list.txt file
https://github.com/cyberwisk/M5Cardputer_WebRadio/blob/main/M5Cardputer_WebRadio/station_list.txt

Based on the libraries:
M5Unified : https://github.com/m5stack/M5Unified
ESP32-audioI2S Version 3.0.13 : https://github.com/schreibfaul1/ESP32-audioI2S

Aurelio

<img width="3768" height="2169" alt="IMG_20260508_171146" src="https://github.com/user-attachments/assets/f7830b1f-385d-4ce9-9125-a81d26a4a661" />

----
WiFi:

With the help of the library [Preferences.h](https://github.com/espressif/arduino-esp32/tree/master/libraries/Preferences) it is now possible to save WiFi settings in the
EEPROM of the StampS3

As soon as the device is turned on, it will ask for the WiFi SSID and password and save them

![image](https://github.com/cyberwisk/M5Cardputer_WebRadio/assets/3136312/531dfc77-a9b6-4a27-82ec-f0d6eeed2621)

---------------
* Required StampS3 settings in the Arduino IDE:

<img width="858" height="912" alt="image" src="https://github.com/user-attachments/assets/e14d7af5-be04-4ffd-b0f8-c96559b7589f" />
