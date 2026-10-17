# AGENTS.md

Instructions for coding agents working in this repo. The README covers use; this file covers how to rebuild, check, and change the project safely.

## What this is

An offline voice loop for five rover commands (Follow, Stay, Fetch, Come, Give), with a small local chat model for other speech. It runs on an Apple Silicon Mac from the terminal, and on the rover's Linux computer as a ROS 2 Jazzy node (`ros/`, [docs/ros2.md](docs/ros2.md)). The input is a microphone or a reSpeaker Flex XVF3800 array reached through a XIAO ESP32S3. Nothing here moves a rover; a command is published, printed, and spoken, and the rover's controller decides what to do.

## Reproduce from a clean checkout

```bash
brew install python@3.12        # once
scripts/setup.sh                # .venv with the pins in requirements.txt
scripts/test                    # unit tests, under 30 s, no hardware or models
scripts/check                   # tests, pyflakes, mypy
scripts/run --text              # typed mode, no microphone
scripts/run --self-test --no-speak   # synthesized speech; downloads models on first run
```

With the reSpeaker Flex connected through the XIAO's USB-C port:

```bash
scripts/setup_firmware.sh       # arduino-cli, esp32 core 3.3.12, audio-tools v1.2.6
scripts/flash_bridge            # build and upload firmware/xiao_mic_bridge
scripts/run --check-array       # must print three PASS lines
scripts/run --input xiao
```

On the rover (Ubuntu 24.04, ROS 2 Jazzy), `scripts/setup_ros.sh` then `source scripts/ros_env.sh`; details and the first-run checklist are in `docs/ros2.md`.

Pinned versions are what the project was tested with: Python 3.12.11, the packages in `requirements.txt`, arduino-cli 1.5.1, esp32 core 3.3.12, audio-tools v1.2.6. `requirements.txt` uses platform markers: MLX on macOS; faster-whisper and NumPy 1.26 on Linux, because Jazzy's message packages are built against NumPy 1.x. Models are downloaded from Hugging Face on first use (Mac: `mlx-community/whisper-base.en-mlx`, `mlx-community/Qwen2.5-0.5B-Instruct-4bit`; Linux: faster-whisper `base.en`, `Qwen/Qwen2.5-0.5B-Instruct`; both: `all-MiniLM-L6-v2`). `ROVER_ASR_BACKEND`, `ROVER_ASR_MODEL`, `ROVER_LLM_BACKEND`, `ROVER_LLM_MODEL`, and `ROVER_TTS` override them.

## Before you finish a change

1. `scripts/check` passes. That runs the tests, pyflakes, and mypy, including `ros/rover_voice_ros`.
2. New behavior has a unit test that uses fakes, not models or devices.
3. For changes to audio capture, the live loop, or firmware, with hardware connected: `scripts/run --check-array`, then a spoken command through `scripts/run --input xiao`. If no hardware is available, say so rather than claiming it works.
4. For changes to `ros/` or to events the node publishes, on a machine with ROS 2 Jazzy: `colcon build --base-paths ros` and `colcon test --packages-select rover_voice_ros`. A Mac has no ROS here; say the ROS side is untested rather than claiming it works.
5. Update `README.md` for user-facing behavior, `docs/respeaker.md` for hardware, firmware, or protocol facts, and `docs/ros2.md` for topics, messages, and parameters.

## Code map

- `events.py`: every user-visible outcome is an event (`Heard`, `CommandAccepted`, `Reply`, `Ignored`, `Status`...). Library code emits events or uses `logging`, never `print`. `ConsoleView` is the terminal output, and `JsonView` is `--json`. Keep the console lines stable, because the tests and the README quote them.
- `cli.py`: flags only; it picks a mode. `runtime.py`: shared startup (`load_asr`, `open_input`, `calibrate_noise`) and `run_live`. `script_test.py` and `selftest.py`: the `--script` and `--self-test` modes.
- `live.py`: `LiveDecoder`, which dispatches commands from partial transcripts and applies the array filters. `session.py`: text in, events out, plus the transcript log in `logs/`.
- Interfaces: `audio/base.py` `Microphone`, `tts/base.py` `Speaker`, `asr/base.py` `ASRBackend`, and `audio/direction.py` `DirectionSource`. They are passed in, not built inside the session or the decoder, so a rover build can swap any of them.
- Backends: `asr/__init__.py` `create_asr` (MLX Whisper on a Mac, faster-whisper on Linux), `tts/__init__.py` `create_speaker` (`say`, espeak-ng), `nlu/llm_chat.py` `create_chat` (MLX, transformers). `config.py` picks by platform.
- `control.py`: `LoopControl`, requests from other threads (`Say`, `TextInput`, `SetListening`), applied by the loop between frames so the session stays single-threaded. `runtime.run_live` takes it; `runtime.run_headless` is the loop without a microphone.
- `ros/rover_voice_msgs`: message definitions. `ros/rover_voice_ros`: `node.py` (voice loop on the main thread, rclpy on a background thread), `mapping.py` (event to message fields with no ROS import; tested in `tests/test_ros_mapping.py`), launch file, params, and a launch test. The core `rover_voice` package must never import ROS.
- `nlu/`: `parser.py` grammar, `spotter.py` early firing on partial transcripts, `meaning.py` embedding match, `llm_chat.py` chat replies.
- `audio/capture.py`: Mac microphone and `open_microphone`, which picks the serial bridge for `--input xiao` or a `/dev/...` path. `audio/serial_capture.py`: bridge protocol, version check, reconnect, and stall recovery; the serial module and port lookup are injectable for tests. `audio/direction.py`: direction tracking and calibration. `audio/vad.py`: loudness gate.
- `firmware/xiao_mic_bridge/`: I2S slave at 48 kHz, decimation to 16 kHz, I2C passthrough, direction frames, protocol version, watchdog.
- Tests in `tests/` use fakes for the speech model, speaker, and array. Follow that pattern; never require a model or device in unit tests.

## Hardware facts that are easy to get wrong

Details and measurements are in `docs/respeaker.md`.

- The XVF3800 firmware is `inthost-lr48-sqr-i2c`: 48 kHz, and the **XVF3800 is the I2S master**. The XIAO must use `is_master = false`. Seeed's wiki says 16 kHz and master; both are wrong for this board, and Seeed's I2S test passes on noise.
- **Do not reflash the XVF3800** (dfu-util, USB firmware). The owner chose to keep its shipped firmware. Only the XIAO is flashed.
- The core board's side USB-C port only supplies power. Data goes through the XIAO's port.
- ROS angles follow REP-103: radians, 0 ahead, positive to the left. The project's own `direction_deg` is clockwise from the front. `mapping.ros_yaw` converts; do not mix them.
- Changing a `.msg` file breaks subscribers on other machines. Add fields rather than renaming, and bump the package version in both `package.xml` files.
- The bridge protocol is versioned (`PROTOCOL_VERSION`, currently 3). Change the firmware and `serial_capture.py` together and bump both, then reflash. The app refuses a mismatched bridge.
- The XIAO's hardware USB serial has a 256-byte TX buffer by default. The firmware raises it to 8192 bytes; a 482-byte frame never sends without that.
- XVF3800 I2C reads often return status 64 (busy). Retry.
- The board has no RGB LEDs. `LED_*` writes are acknowledged but do nothing.
- For direction, trust the auto-select beam angle only while its speech energy is above zero. `DOA_VALUE` lags.
- If an upload fails with "No serial data received", the XIAO needs bootloader mode: hold B while plugging it in. Ask the person to do it; it cannot be done from software.
- `say` plays on the Mac's current output. With headphones, the array cannot hear the rover, and speaker calibration finds nothing.

## Local, untracked state

- `build/`, `install/`, `log/` (colcon output), `.venv/`, `logs/` (transcripts), and `.doa_calibration.json` (per-setup direction calibration, written by `--doa-calibrate`) are ignored by git.
- Calibration needs a person at the board, so an agent cannot complete it alone.

## Style

- Docs: short, plain sentences; say what happens, not how good it is. Match `README.md` and `docs/commands.md`.
- Code: match the surrounding modules. Type hints, short docstrings that say why, few comments.
- Keep the command path fast. The meaning model and the chat model stay off it, and new filters must not delay early commands; measure if unsure.

## Open work

- First build and run on the rover's ROS 2 system: the checklist at the end of `docs/ros2.md`.
- Set the license in the two `package.xml` files and `setup.py`; they say `TODO`.
- Run `--doa-calibrate` with the rover's speaker in place.
- Echo cancellation: send the rover's voice through the XIAO to the board's output so the XVF3800 has a reference, and stop relying on direction and text to ignore the rover's own voice.
