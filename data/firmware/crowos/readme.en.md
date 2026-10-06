# Crow OS
System for M5 Cardputer.
![crowos](https://github.com/JonasLacerda/crowos/assets/65193517/ee262874-0888-4b85-a8d9-d1258c3f7bbb)

The apps I am developing (trying to make work):
- USB Keyboard
  - [x] Partially done, it is functional, but you need to restart the Carputer to return to serial. It only uses the keyboard to input to the device if the keyboard app is on the screen.
  - [x] Improved the brightness shortcut, using opt + b to change brightness. This option is also available in the settings.
- IR
  - [x] In development. My TV is TCL and I haven't found its commands. This requires me to build an Arduino to capture the IR remote inputs and then program them for the Carputer.
  - [ ] customize the controls.
  - [ ] Create a document for configuring each remote on the SD card.
- Time
  - [x] Partially done. I created the functions to set the correct time, and the time runs well. There is a difference of a few seconds that will be corrected with Wi‑Fi in the future.
  - [ ] I want to add the Pomodoro technique to the Time app.
  - [ ] Capture race‑style timings. I think an app like this would be cool to know how long each stage of a problem or production takes.
  - [ ] Even though I lack the patience to do it, I want to create an alarm and add a start function so that it runs a specific program at a given time.
- SD
  - [ ] I cry and tears...
  - [x] Reading the memory card, it's reading...
  - [ ] Make it read a file to load the IR buttons.

Once that's done, I will program the Wi‑Fi and Bluetooth parts. Only after that will I start studying how to adapt the modules. So far, the compiled code is using 20% of the ESP32S3 memory.

note:
```
esptool.py --chip esp32s3 merge_bin --output Crow.bin 0x0000 Crow.ino.bootloader.bin 0x8000 Crow.ino.partitions.bin 0x10000 Crow.ino.bin

esptool.py --port /dev/ttyACM0 write_flash 0x0 Crow.bin
```
