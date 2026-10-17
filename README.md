# Rover voice prototype

Offline voice loop for five spoken rover commands: Follow, Stay, Fetch, Come, and Give. It runs on an Apple Silicon Mac from the terminal, and on the rover's Linux computer as a ROS 2 node ([docs/ros2.md](docs/ros2.md)).

A command does not have to use one fixed sentence. A known phrase is matched directly. Any other wording with the same meaning is matched locally with a small embedding model (`all-MiniLM-L6-v2`). The match is only a command name. Follow distance, holding position, grasping the rock pick hammer, driving to the astronaut, and placing the hammer are not implemented here.

Other speech is answered by Qwen2.5 0.5B Instruct, then spoken with the Mac `say` command (espeak-ng on Linux). The chat model does not choose the command.

## Commands

The accurate wordings, sound-alikes, and the pairs that get confused are in [docs/commands.md](docs/commands.md). A listed phrase is the accurate path. Other wording can still match by meaning, with lower confidence.

| Command | Say |
|---|---|
| Follow | heel, follow me, come with me |
| Stay | stay, sit, stop |
| Fetch | fetch, fetch the hammer |
| Come | here, come here |
| Give | drop, drop it, let go |

## Several commands at once

One breath is one utterance. A command that cannot grow into a different command fires as soon as it is recognized, before the pause at the end. "Come" and "give" wait for a short pause, because "come with me" is Follow and "give me a second" is conversation.

If two different commands are both clear and close in score, neither runs. The rover asks you to repeat one of them. The command already latched stays as it was.

A later command replaces the earlier one. There is no queue. The microphone stays open while the reply plays. Saying a different command cuts off "Okay, follow" and runs the new one. The same command heard from the speakers is ignored.

## Speed

Clear commands are transcribed about five times a second while you are talking, and the grammar match does not wait for the end of the sentence. Chat, and a phrase that is still ambiguous, still wait until 0.18 seconds of silence. The meaning model and the chat model stay off the command path.

A smaller speech model is faster and less accurate. Set it before `scripts/run`:

```bash
ROVER_ASR_MODEL=mlx-community/whisper-tiny.en-mlx scripts/run
```

## Run

Needs an Apple Silicon Mac and Python 3.12 (`brew install python@3.12`). For Linux and ROS 2, see [docs/ros2.md](docs/ros2.md).

```bash
scripts/setup.sh
scripts/test
scripts/run
```

Typed mode, no microphone:

```bash
scripts/run --text
```

Spoken check, including paraphrases:

```bash
scripts/run --self-test --no-speak
```

The speech model loads when listening starts. The meaning model and the chat model load the first time a line is not a known command. The first launch downloads whichever of those models is missing.

Grant microphone access to the terminal app if live listening fails to open the input device. Speech uses the Mac `say` command, so it plays on the current output device. Choose a different microphone with `--input`:

```bash
scripts/run --input "MacBook Pro Microphone"
```

## reSpeaker Flex microphone

The reSpeaker Flex XVF3800 (circular, with XIAO ESP32S3) can replace the Mac microphone. The array cleans up the audio and reports where speech comes from. The XIAO streams both to the Mac over USB. Plug the cable into the XIAO's own USB-C port. The board's side port only supplies power.

One-time setup:

```bash
scripts/setup_firmware.sh
scripts/flash_bridge
scripts/run --check-array
```

Then:

```bash
scripts/run --input xiao       # listen through the array
scripts/run --doa-calibrate    # spoken prompts: stand at the front, then the right; learns the speaker too
scripts/run --doa              # live view of where speech comes from
```

Each heard line gets a `FROM:` line, for example `FROM: → right (88°)`. Before calibration, it shows the board's own angle.

What the array adds to recognition:

- A turn counts only if the array reports speech energy during it. Bumps, clicks and fan bursts are dropped before Whisper runs (`Ignored: the array heard noise, not speech.`). Commands are not delayed.
- While the rover is talking, speech from within 35° of its speaker is treated as its own voice. A person standing next to the speaker cannot interrupt it.
- If the XIAO's USB link drops, listening pauses and resumes when it comes back.

The board has no direction LEDs. Wiring, firmware details, the serial protocol, and measurements are in [docs/respeaker.md](docs/respeaker.md).

## What a command prints

Known phrase:

```text
YOU: follow
SUCCESS: FOLLOW (confidence 0.90)
ROVER: Okay, follow.
COMMAND: FOLLOW
```

Different wording, same meaning:

```text
YOU: walk alongside me
SUCCESS: FOLLOW (confidence 0.83) by meaning
ROVER: Okay, follow.
COMMAND: FOLLOW
```

Say `quit` to exit. Conversation transcripts are appended under `logs/`.

## Events for a rover controller

The session reports everything as typed events (`src/rover_voice/events.py`). The terminal lines above come from one view of those events. `--json` writes them as one JSON object per line on stdout instead. Warnings go to stderr.

```bash
scripts/run --input xiao --json
```

```text
{"event": "Heard", "text": "follow me", "asr_ms": 113.0, "direction": "→ right (88°)", "direction_deg": 88.0, "started_at": 1760630000.25}
{"event": "CommandAccepted", "intent": "FOLLOW", "confidence": 0.97, "by_meaning": false, "slots": {}, "direction": "→ right (88°)", "direction_deg": 88.0, "started_at": 1760630000.25, "text": "follow me"}
{"event": "Reply", "speech": "Okay, follow.", "llm_ms": null}
{"event": "StateChanged", "command": "FOLLOW"}
```

A rover controller acts on `CommandAccepted`. `direction_deg` is clockwise from the rover's front (90 is right) and is null until the array is calibrated. `started_at` is when speech began. In Python, subscribe a function to the session's `EventBus` instead of reading stdout.

Guided live test. Say each line when asked. The Mac speaks the result:

```bash
scripts/test_live
```

The lines are in `scripts/test_lines.txt`. Add `--text` to run those lines without the microphone:

```bash
scripts/test_live --text
```

## ROS 2

On the rover, the same loop runs as a ROS 2 Jazzy node. It publishes `/rover_voice/command` (`rover_voice_msgs/VoiceCommand`), transcripts, replies, the direction of speech, and diagnostics. It accepts `say`, `text_in`, and `set_listening`.

```bash
scripts/setup_ros.sh
source scripts/ros_env.sh
ros2 launch rover_voice_ros voice.launch.py input:=xiao
```

Topics, messages, QoS, parameters, and a controller example are in [docs/ros2.md](docs/ros2.md). It has not been run on a ROS system yet; the first-run checklist is there too.

## Tests

```bash
scripts/test     # unit tests
scripts/check    # unit tests, pyflakes, and mypy
```

The unit tests need no microphone, models, hardware, or ROS. The bridge tests use a fake serial port. The ROS message mapping is tested without ROS; the ROS launch test runs with `colcon test` on the rover. For the array, `scripts/run --check-array` checks the live hardware.

## Layout

| Path | What |
|---|---|
| `src/rover_voice/cli.py` | flags; picks a mode |
| `src/rover_voice/events.py` | event types, event bus, terminal and JSON views |
| `src/rover_voice/runtime.py` | shared startup (speech model, input, noise floor), the live listening loop, and the headless loop |
| `src/rover_voice/control.py` | requests into the loop from other threads: say, text, pause listening |
| `src/rover_voice/live.py` | live decoder: partial transcripts, early commands, array filters |
| `src/rover_voice/session.py` | one line in, command or chat reply out, as events |
| `src/rover_voice/script_test.py`, `selftest.py` | `--script` and `--self-test` modes |
| `src/rover_voice/*/base.py` | interfaces: `Microphone`, `Speaker`, `ASRBackend` |
| `src/rover_voice/asr/` | MLX Whisper (Mac), faster-whisper (Linux), `create_asr` |
| `src/rover_voice/tts/` | `say` (Mac), espeak-ng (Linux), `create_speaker` |
| `src/rover_voice/nlu/` | grammar, sound-alikes, meaning model, chat model |
| `src/rover_voice/audio/` | Mac mic, XIAO serial mic, loudness gate, direction |
| `src/rover_voice/doa_tools.py` | `--check-array`, `--doa`, `--doa-calibrate` |
| `firmware/xiao_mic_bridge/` | XIAO ESP32S3 firmware |
| `ros/` | ROS 2 packages: `rover_voice_msgs`, `rover_voice_ros` |
| `docs/` | command phrases, reSpeaker hardware notes, ROS 2 |
| `scripts/` | setup (Mac, Linux, ROS), tests, run, firmware flashing |
