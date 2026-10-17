# ROS 2

The voice loop runs as a ROS 2 node on the rover's Linux computer. It publishes recognized commands, transcripts, and the direction of speech. It accepts text to speak and text to handle. It does not drive the rover. A controller node subscribes to `command` and decides what to do.

Target: ROS 2 Jazzy on Ubuntu 24.04 (Python 3.12), x86_64 or aarch64.

> Status: written and unit-tested off-robot, but not yet built or run on a ROS system. The first run on the rover is listed under [First run on the rover](#first-run-on-the-rover).

## Setup

```bash
sudo apt install ros-jazzy-ros-base ros-jazzy-diagnostic-msgs ros-jazzy-tf2-ros \
  python3-colcon-common-extensions python3.12-venv espeak-ng ffmpeg libportaudio2
sudo usermod -aG dialout "$USER"     # serial access to the XIAO; log out and back in
source /opt/ros/jazzy/setup.bash
scripts/setup_ros.sh                 # .venv with the Linux pins, then colcon build of ros/
```

In each new shell:

```bash
source scripts/ros_env.sh            # ROS, this workspace, then .venv
ros2 launch rover_voice_ros voice.launch.py input:=xiao
```

`ros_env.sh` activates the venv last, so `python3` is the venv's. The node's script starts with `#!/usr/bin/env python3`, so it runs with the speech packages, and finds `rclpy` and the messages on the `PYTHONPATH` that ROS sets. The venv is created with `--system-site-packages` for the Python packages `rclpy` needs from apt.

On Linux the backends are:

| Part | Mac | Linux |
|---|---|---|
| Speech recognition | MLX Whisper, `mlx-community/whisper-base.en-mlx` | faster-whisper, `base.en` |
| Chat | MLX, `mlx-community/Qwen2.5-0.5B-Instruct-4bit` | transformers, `Qwen/Qwen2.5-0.5B-Instruct` |
| Voice | `say` | `espeak-ng` |
| Meaning model | sentence-transformers `all-MiniLM-L6-v2` | same |

Models download from Hugging Face on first start. On an offline rover, start the node once with a network connection, or copy `~/.cache/huggingface` over.

Environment variables choose other backends: `ROVER_ASR_BACKEND`, `ROVER_ASR_MODEL`, `ROVER_ASR_DEVICE` (`auto`, `cpu`, `cuda`), `ROVER_ASR_COMPUTE` (`int8`, `float16`...), `ROVER_LLM_BACKEND`, `ROVER_LLM_MODEL`, `ROVER_TTS` (`espeak-ng`, `say`, `none`).

NumPy is pinned to 1.26 on Linux, because Jazzy's message packages are built against NumPy 1.x.

On a Jetson, PyPI's aarch64 `torch` runs on the CPU only. For the GPU, install NVIDIA's JetPack build of `torch` into the venv before `scripts/setup.sh`. faster-whisper on CUDA also needs a CUDA build of CTranslate2.

## Topics

The node is named `rover_voice`, so with no namespace the topics are under `/rover_voice/`.

Published:

| Topic | Type | QoS | When |
|---|---|---|---|
| `command` | `rover_voice_msgs/VoiceCommand` | reliable, volatile, depth 10 | a command is accepted |
| `state` | `std_msgs/String` | reliable, transient local, depth 1 | the last command changes (`none` at start) |
| `utterance` | `rover_voice_msgs/Utterance` | reliable, depth 10 | every transcript |
| `reply` | `std_msgs/String` | reliable, depth 10 | the rover speaks |
| `sound_direction` | `rover_voice_msgs/SoundDirection` | sensor data (best effort, depth 5) | about 16 Hz, reSpeaker only |
| `events` | `std_msgs/String` | reliable, depth 50 | every event as JSON, the same as `--json` |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | default | 1 Hz: input, listening, calibration, bridge reconnects |

`command` is volatile on purpose. A controller that starts late does not receive an old command. It can read `state`, which is latched.

Subscribed:

| Name | Type | Effect |
|---|---|---|
| `say` (topic) | `std_msgs/String` | the rover speaks the text. Its own voice is then ignored by the microphone, as with replies. |
| `text_in` (topic) | `std_msgs/String` | handled like a transcript, for typed commands or another speech recognizer |
| `set_listening` (service) | `std_srvs/SetBool` | `false` pauses listening (for example while driving), `true` resumes |

```bash
ros2 topic echo /rover_voice/command
ros2 topic pub --once /rover_voice/say std_msgs/String "{data: 'Battery low.'}"
ros2 topic pub --once /rover_voice/text_in std_msgs/String "{data: 'follow me'}"
ros2 service call /rover_voice/set_listening std_srvs/srv/SetBool "{data: false}"
```

## Messages

`VoiceCommand`: `header`, `intent` (`FOLLOW`, `STAY`, `FETCH`, `COME`, `GIVE`, also as constants), `confidence`, `by_meaning`, `transcript`, `slot_keys`/`slot_values`, `has_direction`, `direction`.

`Utterance`: `header`, `text`, `asr_ms`, `has_direction`, `direction`, `direction_label`.

`SoundDirection`: `header`, `speech`, `energy`, `has_direction`, `direction`, `calibrated`, `board_degrees`.

The full definitions with comments are in `ros/rover_voice_msgs/msg/`.

- **Stamp.** On `command` and `utterance`, the stamp is when the person started speaking, not when recognition finished. Text from `text_in` is stamped on receipt.
- **Direction.** Radians in the REP-103 convention: 0 straight ahead, positive to the left. Right is −π/2. The array calibration (`scripts/run --doa-calibrate`) already turns the angle into the rover's frame.
- **No direction.** `has_direction` is false when there is no direction: a plain microphone, an uncalibrated array, or no speech energy. Check it; `direction` is 0 then, which is not "ahead".
- **Frame.** `frame_id` is `respeaker_link`. The launch file publishes a static transform from `base_link` with the array's position (`x`, `y`, `z`) and no rotation.

## Parameters and launch arguments

| Parameter | Default | |
|---|---|---|
| `input` | `xiao` | `xiao`, `default` (system microphone), a `/dev/ttyACM*` path, a microphone name, or `none` (text on `text_in` only; no speech model loads) |
| `speak` | `true` | speak replies |
| `use_llm` | `true` | answer other speech with the chat model |
| `frame_id` | `respeaker_link` | |
| `asr_backend`, `asr_model` | `""` | empty picks the platform default |
| `log_dir` | `~/.ros/rover_voice` | transcript logs; empty turns them off |

The defaults are in `ros/rover_voice_ros/config/voice.yaml`. The launch file takes `input`, `speak`, `use_llm`, `frame_id`, `namespace`, `params_file`, `parent_frame`, `publish_tf`, and `x`, `y`, `z`. Launch arguments win over the params file.

```bash
ros2 launch rover_voice_ros voice.launch.py input:=xiao x:=0.12 z:=0.30
ros2 launch rover_voice_ros voice.launch.py input:=none speak:=false use_llm:=false
```

The direction calibration file is `.doa_calibration.json` in the repo, or the path in `ROVER_DOA_CALIBRATION`. Run the calibration on the rover with the array mounted: `scripts/run --doa-calibrate`.

## Behavior as a node

- **Quitting.** "Goodbye" and the other quit phrases do not stop the node. They are handled as ordinary speech.
- **Lost USB link.** If the XIAO's link drops, the node keeps running, reconnects, and reports the count in diagnostics.
- **Crashes.** If the node exits, for example because the array is unplugged at start, launch restarts it after 5 s.
- **Stopping.** Ctrl-C and SIGTERM close the microphone cleanly.
- **Speech only.** Nothing here moves the rover. An emergency stop belongs in the controller or the hardware, not in speech recognition.

## A minimal controller

```python
import rclpy
from rclpy.node import Node
from rover_voice_msgs.msg import VoiceCommand


class Controller(Node):
    def __init__(self):
        super().__init__("voice_controller")
        self.create_subscription(VoiceCommand, "/rover_voice/command", self.on_command, 10)

    def on_command(self, msg: VoiceCommand):
        if msg.confidence < 0.8:
            return
        if msg.intent == VoiceCommand.COME and msg.has_direction:
            self.get_logger().info(f"Turn {msg.direction:.2f} rad toward the speaker, then drive.")
        else:
            self.get_logger().info(f"Run {msg.intent}.")


rclpy.init()
rclpy.spin(Controller())
```

## Layout

| Path | What |
|---|---|
| `ros/rover_voice_msgs/` | message package (ament_cmake) |
| `ros/rover_voice_ros/rover_voice_ros/node.py` | the node: voice loop on the main thread, rclpy on a background thread |
| `ros/rover_voice_ros/rover_voice_ros/mapping.py` | events to message fields, angle and stamp conversion; no ROS imports, unit-tested in `tests/` |
| `ros/rover_voice_ros/launch/voice.launch.py` | node plus static transform |
| `ros/rover_voice_ros/test/` | launch test: `text_in` "follow me" comes back on `command` |
| `src/rover_voice/control.py` | thread-safe requests into the voice loop (`say`, text, listening) |

The core package `rover_voice` never imports ROS. The Mac app and the unit tests run without it.

## First run on the rover

None of this has run on ROS yet. In order:

1. `scripts/setup_ros.sh` finishes, and `install/rover_voice_ros/lib/rover_voice_ros/voice_node` starts with `#!/usr/bin/env python3`.
2. `colcon test --packages-select rover_voice_ros && colcon test-result --verbose` passes the launch test.
3. `ros2 launch rover_voice_ros voice.launch.py input:=none speak:=false`, then the `text_in` and `command` examples above.
4. `scripts/run --check-array` on the rover, then `ros2 launch rover_voice_ros voice.launch.py input:=xiao` and say "follow me" while watching `ros2 topic echo /rover_voice/command`.
5. `scripts/run --doa-calibrate` with the array mounted, then check that `direction` is about −1.57 when speaking from the rover's right.
