# Architecture

One offline voice loop recognizes five commands: Follow, Stay, Fetch, Come, and Give. It prints the command, speaks a short reply, and publishes the command. It does not drive the rover. A controller, later, decides what the rover does.

The same loop runs two ways:

- On a Mac, from the terminal (`scripts/run`).
- On the rover's Linux computer, as a ROS 2 Jazzy node (`ros/`).

The core package `rover_voice` never imports ROS. ROS is a shell around the same session.

```text
microphone or XIAO bridge
        |
        v
  loudness gate (vad) ---- direction, if the array is connected
        |
        v
  live decoder  --partial text--> grammar spotter --> session
        |                              |
        |                         meaning model, only if the grammar says chat
        |                              |
        v                              v
  finished clip --> Whisper -----> session
                                      |
                    +-----------------+------------------+
                    |                 |                  |
                 events            speaker            JSONL log
                    |
         +----------+-----------+
         |                      |
    terminal / --json      ROS 2 node
```

## Systems

| System | Owns | Talks to | Detail |
|---|---|---|---|
| Voice core | commands, chat, events, the live loop | microphone, speech model, speaker | this file |
| Commands | the five intents and the phrases that count | the live decoder, through the parser | [commands.md](commands.md) |
| Microphone array | 16 kHz audio and direction from the reSpeaker Flex | the voice core, over USB serial | [respeaker.md](respeaker.md) |
| ROS 2 | topics, services, diagnostics | the voice core, through `LoopControl` and events | [ros2.md](ros2.md) |
| Open work | what has not been run together yet | all of the above | [TODO.md](TODO.md) |

## Voice core

`src/rover_voice/`. Library code emits events or writes logs. It does not print. `ConsoleView` is the terminal. `JsonView` is `--json`.

| Module | Role |
|---|---|
| `cli.py` | Flags only. Picks text mode, live mode, the script, the self-test, or an array tool. |
| `runtime.py` | Loads the speech model, opens the input, learns the noise floor, then runs `run_live` or `run_headless`. |
| `live.py` | `LiveDecoder`. Feeds 30 ms frames. Transcribes while speech continues. Fires a stable command before the pause. Applies the array filters. |
| `session.py` | One transcript in. Events and a spoken reply out. Loads the meaning model and the chat model only when a line is not already a command. |
| `events.py` | `Heard`, `CommandAccepted`, `Reply`, `StateChanged`, `Ignored`, `Clarify`, `Status`, `SessionEnded`. `EventBus` delivers them. |
| `control.py` | `Say`, `TextInput`, `SetListening`. Other threads queue these. The loop applies them between frames, so the session stays on one thread. |
| `config.py` | Sample rate, endpoint timing, score thresholds, and which backend the platform uses. |
| `script_test.py`, `selftest.py` | `scripts/test_live` and `--self-test`. |
| `doa_tools.py` | `--check-array`, `--doa`, `--doa-calibrate`. |

Interfaces, passed in rather than built inside the session:

| Interface | File | Implementations |
|---|---|---|
| `Microphone` | `audio/base.py` | Mac mic (`audio/capture.py`), XIAO bridge (`audio/serial_capture.py`) |
| `Speaker` | `tts/base.py` | `say` on a Mac, espeak-ng on Linux, or none |
| `ASRBackend` | `asr/base.py` | MLX Whisper on a Mac, faster-whisper on Linux |
| `DirectionSource` | `audio/direction.py` | the bridge's direction tracker, or nothing |

### Command path

`nlu/parser.py` is the accurate path. A listed phrase or a lone command word becomes Follow, Stay, Fetch, Come, or Give. The chat model never chooses a command.

`nlu/spotter.py` decides whether that result is safe to fire before the person finishes. "Come" and "give" wait for a short pause, because the next word can change them. "Heel" and "follow me" fire immediately.

`nlu/understanding.py` calls the parser first. Only a line the parser calls chat goes to `nlu/meaning.py` (`all-MiniLM-L6-v2` on CPU). A weak or close meaning match stays chat or asks for a repeat.

`nlu/llm_chat.py` answers conversation. Qwen2.5 0.5B Instruct, 4-bit on a Mac, full weights on Linux. It loads on the first non-command. A reply that itself looks like a command is replaced with a fixed sentence. Spoken services (a fixed "what can you do", status, repeat) are milestones in [TODO.md](TODO.md). They stay off the model, and the model stays off the command path.

`rover/arbiter.py` turns a parse into "Okay, follow." and latches the command name. It does not move the rover.

### Audio path

`audio/vad.py` turns 30 ms frames into speech. It needs three loud frames to start and 0.18 s of silence to end a clip. Short words are kept (about 0.09 s). The noise floor is learned at startup.

`audio/health.py` watches the same frames. No frames for 2 seconds, a clipped signal, or a stalled reSpeaker is an error. Digital silence for 3 seconds is a warning. The terminal prints the change. On ROS the same report is `/diagnostics`, and the values `audio`, `audio_rms`, and `audio_peak` stay on the status. The loop keeps listening. That report is about the microphone. Listening to the rover's own machines for a fault is a later milestone in [TODO.md](TODO.md). It is not built.

`live.py` also sends the audio so far to Whisper about every 0.2 s once 0.16 s of speech is in the buffer. A stable command does not wait for the 0.18 s end.

While a reply is playing, the microphone stays open. A different command interrupts the reply. The same command, heard again from the speakers, is ignored. With the array, speech from within about 35° of the rover's speaker is ignored while the rover is talking.

## Microphone array

The reSpeaker Flex XVF3800 does beamforming and noise suppression. The XIAO ESP32S3 is an I2S slave at 48 kHz, decimates to 16 kHz, and sends USB serial frames plus a direction frame about every 60 ms. Firmware is `firmware/xiao_mic_bridge/`. Protocol version is 3. The app refuses a different version.

`audio/serial_capture.py` reads the port, checks the version, reconnects if USB drops, and asks the bridge to stream again if audio stalls for 2 s. `audio/direction.py` keeps the recent angles and the calibration in `.doa_calibration.json` (`ROVER_DOA_CALIBRATION` moves that file).

Angles inside the project are clockwise from the front. ROS converts them. See [respeaker.md](respeaker.md).

The array is optional. A Mac microphone has no direction. The live decoder then skips the speech-energy check and the speaker-direction check.

## ROS 2

`ros/rover_voice_msgs` holds the messages. `ros/rover_voice_ros` is the node.

`node.py` runs the voice loop on the main thread and rclpy on a background thread. Incoming `say`, `text_in`, and `set_listening` become `LoopControl` requests. Outgoing events become topics. `mapping.py` converts event fields and angles and does not import ROS, so the Mac tests cover it.

The node publishes `command`, `state`, `utterance`, `reply`, `sound_direction`, `events`, and `/diagnostics`. Quit phrases do not stop the node. Nothing in the node drives the rover. See [ros2.md](ros2.md).

## Models and platforms

| Part | Mac | Linux (rover) |
|---|---|---|
| Speech | MLX Whisper `mlx-community/whisper-base.en-mlx` | faster-whisper `base.en` |
| Meaning | `all-MiniLM-L6-v2` on CPU | same |
| Chat | MLX `Qwen2.5-0.5B-Instruct-4bit` | transformers `Qwen/Qwen2.5-0.5B-Instruct` |
| Voice | `say` | espeak-ng |

`ROVER_ASR_BACKEND`, `ROVER_ASR_MODEL`, `ROVER_LLM_BACKEND`, `ROVER_LLM_MODEL`, and `ROVER_TTS` override them. Models download from Hugging Face on first use.

## Flows

### A clear command

1. Frames pass the loudness gate. With the array, the turn also needs speech energy in that window.
2. After about 0.16 s of speech, Whisper transcribes the audio so far.
3. The spotter accepts the phrase, or waits if the next word could change it.
4. The session emits `Heard`, `CommandAccepted`, `Reply`, and `StateChanged`.
5. The speaker starts "Okay, follow." and listening continues.
6. On ROS, `CommandAccepted` is published on `command`. The stamp is when speech started.

### A sentence that is not a listed phrase

1. The clip ends after 0.18 s of silence. Partials did not fire.
2. The parser returns chat.
3. The meaning model loads if this is the first time, then scores the line.
4. A clear meaning emits `CommandAccepted` with `by_meaning` set. A close call emits `Clarify`. Anything else goes to the chat model, which emits `Reply`.

### The rover talks

1. A reply, or a ROS `say`, starts the speaker and marks the loop as speaking.
2. A new turn that is the same command, or that comes from the speaker's direction, is dropped.
3. A different command interrupts the speaker and replaces the latched command.

### Typed input and a quiet rover

`--text` and ROS `text_in` call `session.handle_text` with no microphone. `input:=none` uses `run_headless`: no speech model, only `Say` and `TextInput`.

### Array check

`--check-array` opens the bridge, checks the protocol version, and confirms audio and direction frames. It does not run the command loop. `--doa` prints the live angle. `--doa-calibrate` stores front, right, and the speaker direction.

## What crosses a boundary

| From | To | Contract |
|---|---|---|
| XIAO firmware | `serial_capture.py` | protocol version 3. Audio `A5 5A`, direction `A5 5C`, version `A5 5D`. |
| `LiveDecoder` | `RoverSession` | one transcript, plus optional direction and start time |
| `RoverSession` | listeners | events in `events.py`. Console lines stay stable; tests and the README quote them. |
| `mapping.py` | ROS messages | intent string, confidence, slots, REP-103 yaw, stamp |
| Controller | this repo | subscribes to `command`. This repo does not subscribe to motion topics. |

A change to a `.msg` field breaks subscribers on other machines. Add fields rather than renaming them, and bump both `package.xml` versions. A change to the bridge protocol must change the firmware and `serial_capture.py` together, then the XIAO has to be reflashed.
