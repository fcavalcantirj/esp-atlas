# AI_StackChan2_README
AI StackChan 2 usage guide.
<br><br>
Features of AI StackChan 2<br>

* Uses the web version of VOICEVOX for speech synthesis.
* Allows you to choose either "Google Cloud STT" or "OpenAI Whisper" for speech recognition.
<br>

Google Cloud STT was referenced from "MhageGH"'s [esp32_CloudSpeech](https://github.com/MhageGH/esp32_CloudSpeech/ "Title"). Thank you.
For enabling "OpenAI Whisper", many thanks to "Inaba" and "kobatan" for their valuable advice.
The wake‑word functionality uses "MechaUma"'s [SimpleVox](https://github.com/MechaUma/SimpleVox/ "Title") library.

---

### How to obtain a ChatGPT API key ###

The method to obtain a ChatGPT API key is as follows (see the link at the bottom of this page for details):

* Visit the [OpenAI website](https://openai.com/ "Title") and create an account. An email address and phone number are required.
* After creating the account, issue an API key. The API key is paid, but there is a free trial period and credits.
<br>

### How to obtain a Web VOICEVOX API key ###

* For the Web VOICEVOX API key, refer to the bottom of this page ([ttsQuestV3Voicevox](https://github.com/ts-klassen/ttsQuestV3Voicevox/ "Title")).
After obtaining the VOICEVOX API key, be sure to register it for "VOICEVOX API usage". Otherwise speech synthesis will not be fast and the audio will be choppy.

### How to obtain a Google Cloud Speech‑to‑Text API key (not required when using Whisper) ###

The method to obtain a Google Cloud Speech‑to‑Text API key is as follows (see the link at the bottom of this page for details):

* Visit the [Google Cloud Platform website](https://cloud.google.com/?hl=ja/ "Title") and create an account. An email address and phone number are required. A credit‑card registration is mandatory, but there is a free trial and free tier.
* After creating the account, obtain an API key.
Enable Speech‑to‑Text for that API key.
<br>
---

### Configuration ###

* Create the following two files in the root of the SD card to enable operation. Once confirmed to work correctly, be sure to remove the SD card used for configuration.

1. **wifi.txt** file: The file name must be "wifi.txt" and its contents are as follows:
YOUR_WIFI_SSID
YOUR_WIFI_PASS

2. **apikey.txt** file: The file name must be "apikey.txt" and its contents are as follows:
YOUR_OPENAI_APIKEY
YOUR_VOICEVOX_APIKEY
YOUR_STT_APIKEY

* **Note**
"YOUR_STT_APIKEY" should contain either the Google Cloud STT API key **or** the same value as "YOUR_OPENAI_APIKEY".
If you set "YOUR_STT_APIKEY" to the same value as "YOUR_OPENAI_APIKEY", OpenAI Whisper will be used for speech recognition.

* If the M5Stack has previously connected to Wi‑Fi, the SD card is not required and it will automatically connect. In this case, you can set the API keys by accessing "http://XXX.XXX.XXX.XXX/apikey" in a browser (replace xxxx.xxxx.xxxx.xxxx with the IP address shown at startup).

### How to use the wake‑word (Core2 only) ###

1. **Register a wake‑word**
Press and hold button B for 2 seconds.
When "Wake‑word registration start" is displayed, speak the desired wake‑word.
If registration succeeds, the registered wake‑word will be played back (the playback volume is low but acceptable). Retry if it fails.

2. **Operation check**
Press button A to enable the wake‑word.
Speak the registered wake‑word. If it is recognized, the device will wait for voice input.
If it never works, repeat step 1.

3. **Additional notes**
- The wake‑word function is disabled on power‑up; enable it with button A when needed.
- Touch the left‑center area of the LCD screen to toggle "monologue mode".

### How to use other features ###

* Touch near the top of the StackChan head to start recording from the microphone; after about 7 seconds the speech is recognized and you can converse.

* You can set the default speaker (voice) via URL, e.g. `http://xxxx.xxxx.xxxx.xxxx/setting?speaker=1` (values 0‑60; the list is at the bottom of this document).

* For temporary voice changes, specify the `voice` parameter in the URL, e.g. `http://192.168.11.20/chat?voice=4&text=こんにちは`.

* Access `http://xxxx.xxxx.xxxx.xxxx/role` in a browser to set a role. Submitting an empty text area deletes the previously set role. Role information is automatically saved to SPIFFS.

* Access `http://xxxx.xxxx.xxxx.xxxx/role_get` to retrieve the currently set role.

* Adjust speaker volume, e.g. `http://xxxx.xxxx.xxxx.xxxx/setting?volume=180` (volume range 0‑255).

* A "monologue mode" has been added: the device speaks at random intervals with random content. It is fun when combined with the emotion expression feature. Touch the left‑center area of the LCD screen to toggle this mode on/off. Even in monologue mode you can still converse from a smartphone.

* Touch the central area of the M5Stack Core2 screen to stop the StackChan neck‑shake.

* Press button C on the M5Stack Core2 to test speech synthesis.

That concludes the usage instructions for AI StackChan.
<br>
### Note: If you flash the firmware with M5Burner, remember to set the API keys again from the SD card. ###
<br>
---

### Reference links for obtaining a ChatGPT API key ###

* [Simple guide to using the ChatGPT API](https://qiita.com/mikito/items/b69f38c54b362c20e9e6/ "Title")<br>

### Reference links for obtaining a Web VOICEVOX API key ###

* See the bottom of this page ([ttsQuestV3Voicevox](https://github.com/ts-klassen/ttsQuestV3Voicevox/ "Title")) for instructions.

### Reference links for obtaining a Google Cloud Speech‑to‑Text API key ###

* [How to obtain/register a Speech‑to‑Text API key](https://nicecamera.kidsplates.jp/help/feature/transcription/apikey/ "Title")<br>

### Reference links for ChatGPT character settings ###

* [Trying character settings with the ChatGPT API](https://note.com/it_navi/n/nf5f702b36a75#8e42f887-fb07-4367-9f3f-ab7f119eb064/ "Title")<br>
<br>
### VoiceVox speaker numbers ###

* VoiceVox speaker number list
 0: Shikoku Metan (sweet)
 1: Zundamon (sweet)
 2: Shikoku Metan (normal)
 3: Zundamon (normal)
 4: Shikoku Metan (sexy)
 5: Zundamon (sexy)
 6: Shikoku Metan (tsuntsun)
 7: Zundamon (tsuntsun)
 8: Kasukabe Tsumugi (normal)
 9: Namioto Ritsu (normal)
10: Amiharu Hau (normal)
11: Genno Takehiro (normal)
12: Shirakami Kotarou (normal)
13: Aoyama Ryusei (normal)
14: Meimei Himari (normal)
15: Kyushu Sora (sweet)
16: Kyushu Sora (normal)
17: Kyushu Sora (sexy)
18: Kyushu Sora (tsuntsun)
19: Kyushu Sora (whisper)
20: Mochiko (cv Asuha Yomogi)
21: Kenzaki Shiyuu (normal)
22: Zundamon (whisper)
23: WhiteCUL (normal)
24: WhiteCUL (fun)
25: WhiteCUL (sad)
26: WhiteCUL (cry)
27: Goki (human ver.)
28: Goki (plushie ver.)
29: No.7 (normal)
30: No.7 (announcement)
31: No.7 (storytelling)
32: Shirakami Kotarou (yay)
33: Shirakami Kotarou (shaky)
34: Shirakami Kotarou (angry)
35: Shirakami Kotarou (cry)
36: Shikoku Metan (whisper)
37: Shikoku Metan (hush hush)
38: Zundamon (hush hush)
39: Genno Takehiro (joy)
40: Genno Takehiro (tsungire)
41: Genno Takehiro (sadness)
42: Chibi‑style Ji (normal)
43: Sakura‑ka Miko (normal)
44: Sakura‑ka Miko (second form)
45: Sakura‑ka Miko (loli)
46: Sayo (normal)
47: Nurse‑Robot Type T (normal)
48: Nurse‑Robot Type T (easy)
49: Nurse‑Robot Type T (fear)
50: Nurse‑Robot Type T (secret talk)
51: †Saint Knight Kurenai† (normal)
52: Suzumatsu Akashi (normal)
53: Kirishima Soryin (normal)
54: Harunaga Nana (normal)
55: Neko‑tsukai Al (normal)
56: Neko‑tsukai Al (calm)
57: Neko‑tsukai Al (cheerful)
58: Neko‑tsukai Bii (normal)
59: Neko‑tsukai Bii (calm)
60: Neko‑tsukai Bii (shy)
<br><br>
