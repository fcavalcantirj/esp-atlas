# M5Claw

M5Claw is an AI assistant firmware that runs on the M5Stack Cardputer, built around `ESP32‑S3 + SPIFFS + PlatformIO + Xiaomi MiMo`. It provides a local companion UI, keyboard chat, voice input, voice playback, WeChat integration, weather display, scheduled tasks, memory files, and skill‑extension capabilities.

The project targets a "flash‑once‑and‑run‑long‑term" form factor rather than a one‑off demo. The repository already contains the firmware code, SPIFFS data, and a one‑click flashing script.

## Feature Overview

- Local companion home page: shows time, battery level, weather, and features a dynamic sunset scene switch.
- Keyboard chat: locally type questions and see AI replies streamed.
- Voice input: on the chat page hold `Fn` to record; release to upload the audio to MiMo for recognition and reply generation.
- TTS playback: the local reply corresponding to a voice input automatically triggers MiMo TTS playback.
- WeChat integration: supports WeChat bots using the iLink protocol, capable of sending/receiving messages, QR‑code pairing, and proactive pushes.
- Image message handling: images received from WeChat are downloaded to a temporary local file and fed to the model as multimodal input.
- Local memory and role setting: persist personality, user info, and long‑term memory via `SOUL.md`, `USER.md`, `MEMORY.md`.
- Skill system: automatically loads `data/skills/*.md` at startup as additional prompt‑based skills.
- Scheduled tasks: supports creating periodic and one‑time tasks; when triggered, tasks can push results locally or to WeChat.
- Heartbeat check: periodically reads `HEARTBEAT.md`; when pending items are found, it automatically triggers the Agent.
- Weather display: uses Open‑Meteo for geolocation parsing and real‑time weather retrieval.
- Serial configuration: supports a serial CLI and is compatible with the M5Burner‑style NVS configuration protocol.

## Tech Stack

- Hardware: M5Stack Cardputer
- MCU: ESP32‑S3
- Firmware framework: Arduino on PlatformIO
- Main libraries:
  - `M5Cardputer`
  - `ArduinoJson`
  - `WebSockets`
- Model service: Xiaomi MiMo
- Weather service: Open‑Meteo
- File system: SPIFFS

## Repository Structure

```text
.
├─ src/                   firmware source code
├─ data/
│  ├─ cert/               TLS certificate bundle
│  ├─ config/             personality and user data
│  ├─ memory/             long‑term memory
│  └─ skills/             built‑in skills
├─ flash.py               one‑click flashing script
├─ platformio.ini         PlatformIO build configuration
├─ partitions.csv         partition table
```

## Environment Requirements

- An M5Stack Cardputer
- Python 3
- PlatformIO CLI, or VS Code with the PlatformIO extension installed
- A 2.4 GHz Wi‑Fi network
- Xiaomi MiMo API Key
- Optional: WeChat iLink bot `token + host`

## Quick Start

### 1. Install Dependencies

Make sure the following commands are available on your host machine:

```powershell
python --version
pio --version
```

If you are on Windows and `python` is not available, you can use `py -3` instead.

### 2. Flash the Firmware

It is recommended to use the script provided in the repository:

```powershell
python flash.py
```

The script will automatically perform:

1. Scan serial ports
2. Erase Flash
3. Compile the firmware
4. Upload the firmware
5. Upload SPIFFS data

If you prefer to do it manually:

```powershell
pio run
pio run -t upload --upload-port COMx
pio run -t uploadfs --upload-port COMx
```

View serial logs:

```powershell
pio device monitor -b 115200
```

If the upload fails, you can try putting the device into download mode and retry: hold `G0`, press `RST` once, then release `G0`.

## First‑Boot Process

After power‑on, the device initializes in the following order:

1. Mount SPIFFS
2. Read NVS configuration
3. Initialize runtime configuration
4. Initialize memory, skills, tools, WeChat, timers, and Agent
5. If the configuration is complete, it automatically connects to the network; otherwise it enters Setup mode

During the first boot, the onboard Setup runs:

- Sequentially input Wi‑Fi, MiMo Key, model name, city
- `Enter` confirms the current field
- `Del` deletes a character
- `Tab` skips and enters offline mode

## Device Operation

### Companion Page

- `Tab`: enter chat page
- `Ctrl`: enter WeChat status page
- Single press `Fn`: toggle sunset scene
- `Fn + R`: clear current Wi‑Fi and re‑enter configuration

### Chat Page

- Normal keyboard input: edit message
- `Enter`: send message
- `Del`: delete character
- `Tab`: scroll chat history up
- `Ctrl`: scroll down; if already at the bottom, return to Companion page
- `Alt`: return to Companion page
- Hold `Fn`: start recording
- Release `Fn`: stop recording and send voice
- `Fn + C`: cancel current model generation

### WeChat Status Page

- Press `Ctrl` from Companion page to enter
- `Tab`: return to Companion page
- `Enter`: retry pairing if it failed
- If not configured, it will attempt to launch QR‑code pairing

### Network‑Failure Page

- `Enter`: retry network connection
- `Fn + R`: reset Wi‑Fi
- `Tab`: enter offline mode

## WeChat Function Details

The project includes a built‑in WeChat bridge based on the iLink protocol:

- Supports QR‑code pairing to obtain `bot_token`
- Also supports setting `token` and `host` directly via serial
- Text messages from WeChat are fed to the Agent
- Images from WeChat are downloaded to a temporary SPIFFS file and used as multimodal input
- Model replies are automatically sent back to the corresponding user
- The model can also proactively send messages to specific users using the `wechat_send` tool

WeChat polling and voice recording/model invocation are paused and resumed to avoid memory contention.

## Built‑in Tools

During runtime, the Agent can invoke the following device‑side tools:

- `get_current_time`
- `read_file`
- `write_file`
- `edit_file`
- `list_dir`
- `cron_add`
- `cron_list`
- `cron_remove`
- `wechat_send`

In addition, MiMo enables a built‑in `web_search`.

## Persistent Files

The following files reside in the device's SPIFFS:

- `data/config/SOUL.md`: assistant personality and values
- `data/config/USER.md`: user profile
- `data/memory/MEMORY.md`: long‑term memory
- `data/skills/*.md`: skill files

During operation, the device also generates:

- `/sessions/*.jsonl`: conversation history saved per session
- `/cron.json`: scheduled tasks
- `/HEARTBEAT.md`: heartbeat task source file
- `/tmp_voice.wav`: temporary voice file
- `/tmp_wx_*.bin`: temporary WeChat image files

If you modify files under `data/`, you need to re‑execute:

```powershell
pio run -t uploadfs --upload-port COMx
```

## Serial Commands

Available in the serial monitor:

```text
help
set_wifi <ssid> <pass>
set_mimo_key <key>
set_mimo_model <model>
set_city <city>
set_wechat <token> <host>
show_config
reset_config
reboot
```

The project also implements M5Burner‑compatible `CMD::GET / CMD::SET / CMD::LIST / CMD::INIT` configuration protocols, making it easy for graphical tools to write parameters directly.

## Configuration Recommendations

- Use `SOUL.md` to define the device's personality, including style, boundaries, and behavioral principles.
- Use `USER.md` to store user nickname, language preference, timezone, location, etc.
- Use `MEMORY.md` to keep long‑term facts such as habits, preferences, plans.
- Store task‑specific operation guides (e.g., daily reports, weather, translation, reminders) in `skills/*.md`.

## Notes

- The local screen channel is limited to "as concise as possible" in system prompts, so local replies are usually shorter than WeChat replies.
- When the device is offline, you can still access the Companion page, but AI, weather, WeChat, and other network‑dependent features are unavailable.
- After modifying `data/skills`, `data/config`, or `data/memory`, simply re‑uploading the firmware is not enough; you must also re‑upload SPIFFS.
- The certificate file `data/cert/x509_crt_bundle.bin` is required for HTTPS access; do not delete it.
- The partition table allocates a large space for SPIFFS to accommodate skills, memory, sessions, and temporary media files.

## License

This project is licensed under `GPL-3.0`; see the [LICENSE](LICENSE) for details.
