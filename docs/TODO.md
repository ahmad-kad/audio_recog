# TODO

What is still open for integration, testing, robustness, and reliability. The unit tests (`scripts/test`, `scripts/check`) do not cover hardware, models under load, or a live ROS graph.

## Integration

The voice loop, the array, and ROS have not been run together on the rover.

- [ ] On the rover (Ubuntu 24.04, ROS 2 Jazzy): `scripts/setup_ros.sh`, then `colcon test --packages-select rover_voice_ros`. A Mac cannot run this.
- [ ] `ros2 launch rover_voice_ros voice.launch.py input:=none speak:=false`, then publish `text_in` "follow me" and see `command`.
- [ ] `scripts/run --check-array` on the rover, then `input:=xiao` and a spoken "follow me" on `/rover_voice/command`.
- [ ] `scripts/run --doa-calibrate` with the array mounted and the rover's speaker in place. Confirm a voice from the rover's right is about −1.57 rad on `command.direction`.
- [ ] Copy the Hugging Face cache onto the rover, or do one online first start, so later boots work with no network.
- [ ] On a Jetson, install NVIDIA's JetPack `torch` before `scripts/setup.sh` if the chat model should use the GPU. PyPI's aarch64 torch is CPU-only. faster-whisper on CUDA needs a CUDA build of CTranslate2.
- [ ] A controller node that subscribes to `command` and does not live in this repo. This package still must not move the rover.
- [ ] Set the license. Both `package.xml` files and `ros/rover_voice_ros/setup.py` say `TODO`.

The checklist with the exact commands is at the end of [ros2.md](ros2.md).

## Testing

Unit tests use fakes. They do not open a microphone, load Whisper, or start rclpy, except the ROS launch test which only runs under `colcon test`.

- [ ] One recorded-audio test: a fixed 16 kHz clip of "follow me" through `LiveDecoder` and a fake session, so a Whisper or VAD change cannot pass while dropping the command. Keep it free of a model download if the ASR is faked; add a separate optional test that uses the real model when the cache is present.
- [ ] A serial-capture test that replays a stalled stream and a dropped port, not only a clean fake port. The reconnect and the 2 s stall recovery need a scripted port that stops, then resumes.
- [ ] `colcon test` result saved from the rover, including the launch test that publishes `text_in` and reads `command`.
- [ ] A spoken pass of `scripts/test_live` on the Mac with the XIAO connected, after a code change to capture, the live loop, or the firmware. If no array is plugged in, say so. Do not treat `scripts/test` as that check.
- [ ] Direction: a test that speech energy gates the angle, and that `DOA_VALUE` is not used while the auto-select beam energy is zero.
- [ ] ROS angle: a right-side sample stays −π/2 after `mapping.ros_yaw`, and `has_direction` is false when the array is uncalibrated.
- [ ] Self-test (`scripts/run --self-test --no-speak`) on the rover once, so faster-whisper and espeak-ng are known to load.

## Robustness

The loop should keep running when a piece fails.

- [ ] Unplug the XIAO while `input:=xiao` is running. The node should stay up, log the drop, reconnect, and count it on `/diagnostics`. This is implemented and covered with a fake port. It has not been confirmed on the cable. A dead stream, clipping, and digital silence are already reported (`audio/health.py`, on the terminal and on `/diagnostics`). Confirm those three on the real cable.
- [ ] Start the node with the array unplugged. Launch should restart it after 5 s. Confirm that restart does not leak serial ports.
- [ ] Whisper throws on one clip. Listening continues and the next command still works. `LiveDecoder` catches that error. Add a test that the fake ASR raises once, then returns "stay".
- [ ] The chat model fails to download or to load. Commands still work and chat uses the fixed sentence. Confirm on a machine with no model cache.
- [ ] A long USB stall (bridge alive, no frames for more than 2 s) sends the start command again and audio resumes.
- [ ] SIGTERM and Ctrl-C close the serial port. Confirm with `lsof` on the rover after a stop.
- [ ] `set_listening` false drops frames and does not leave a half-open utterance that fires when listening resumes.
- [ ] Two `say` requests close together: the second interrupts the first, and the microphone does not treat either sentence as a command.

## Reliability

Wrong commands and missed commands.

- [ ] Keep the command list small. A new phrase needs a parser test that names the intent, plus a test that the nearby confusing sentence stays chat or stays the other intent. The list is [commands.md](commands.md).
- [ ] Measure the live path on the target machine: time from end of speech to `CommandAccepted` for "heel", "stay", "come here", and "give me the hammer". The partial path should beat the 0.18 s endpoint for "heel" and "follow me". Record the numbers. Do not tune from memory.
- [ ] Run the meaning model on a fixed list of ordinary sentences ("what time is it", "good morning", "follow the instructions", "let's go", "down") and confirm none become a command.
- [ ] Echo. The array ignores speech from the speaker's direction, and the text path ignores the same command while the reply plays. A person standing next to the speaker cannot interrupt. Echo cancellation is not wired: the firmware sends silence as the XVF3800 reference. Sending the rover's voice out the board's playback path is the real fix. Until then, do not claim the rover cannot hear itself from every angle.
- [ ] Recalibrate direction after the array is remounted. An old `.doa_calibration.json` points the wrong way and will hide the astronaut or treat them as the speaker.
- [ ] Do not put the chat model on the command path. It has been tried. It labels too many lines as Come.
- [ ] Whisper `initial_prompt` stays off. It biased short audio toward "follow".
- [ ] Protocol and messages: firmware and `serial_capture.py` stay on version 3 together. ROS fields are added, not renamed.

## Chat with the rover

Potential milestones. The chat path is separate from commands. Today a non-command goes to Qwen, one short sentence, with the last command name in the prompt. The model must not choose or confirm a command. Fixed replies are more reliable than the model for anything the rover should say the same way every time.

### Conversation

How it feels to talk to it, not new commands.

- [ ] Write the turns people actually say: greet, ask what it can do, ask it to repeat, correct a mishear ("no, stay"), and stop the chat. Put them in a script next to `scripts/test_lines.txt` and score chat versus command, so a phrase change cannot steal a command.
- [ ] Repair. After `Clarify`, the next line is the correction, not a fresh chat. "No, stay" after a bad guess becomes Stay. A test covers that pair.
- [ ] Address. With the array calibrated, answer when speech is toward the rover. Side talk at another angle stays `Ignored` and does not start the chat model. Without a calibration, keep answering, as it does now.
- [ ] One voice. Replies stay one spoken sentence. The same command is not said back as if the rover had already moved. The existing guard that replaces a short command-shaped reply stays.
- [ ] Barge-in is the interruption policy. A person can cut off a chat reply with a command. A chat reply does not cut off a command that was just accepted.
- [ ] History stays short (a few turns). A new ROS session or a long pause starts a fresh history so yesterday's chat is not in today's prompt. One list, shared by everyone, until the per-person store below exists.

### Several people

The array gives a direction, not a name. The XVF3800 sends one beamformed stream, so two people talking at once become one clip. Turns that do not overlap can be kept apart. The rover still has one latched command.

- [ ] Store each chat turn with the direction sector it came from (front, left, right, back) and the time. The JSONL log already records the line. Add the sector to that record. No voice enrollment yet.
- [ ] Separate conversations. The chat prompt for a reply uses only the recent turns from that same sector, plus the one shared command. A person on the left does not hear the right-hand chat quoted back. Sectors older than a few minutes are dropped. Someone who walks to a new side starts a new thread.
- [ ] One conversation, several people. A mode that keeps a single history and prefixes each turn with its sector ("person on the right: ..."), so the reply can refer to who just spoke. This is the group talk. It is not the same as separate threads. Pick the mode per session. The default stays one shared history until a mode is chosen.
- [ ] Voice identity, after direction buckets work. A person says a fixed enrollment line once. Later turns match a short voice embedding and keep their thread when they move. Similar voices and a bad enrollment stay on direction. Enrollment audio stays on the robot. It is not sent out.
- [ ] Overlapping talk stays one utterance. Do not promise a transcript per person while they speak together. The beamformer already picks one stream. A second microphone, or a model that separates voices, is a different project.
- [ ] Commands stay global. "Follow" from one person and "stay" from another in one breath still clarify, as they do now. A chat thread does not get its own Follow.

### Services

Spoken questions that should hit a fixed answer or a ROS read, not the chat model. The model can still handle everything else.

- [ ] A small spoken menu, matched like commands and answered with a fixed line: "what can you do", "repeat that", "what did I just say", "are you listening", "be quiet", "you can talk". Each has a parser test. None of them is Follow, Stay, Fetch, Come, or Give.
- [ ] "What did you hear" speaks the last transcript. "What was the command" speaks the latched command. Both come from session state, not from the model.
- [ ] Status from the node, when ROS is up: listening or paused, microphone name, bridge connected, direction calibrated. A spoken "status" reads that. It does not invent battery, position, or speed. Those wait until a controller publishes them.
- [ ] Subscribe to a later status topic (battery, mode, fault) and add one sentence to the fixed status reply. Until that topic exists, the rover says it does not know.
- [ ] `say` remains the way another node makes the rover speak. A service reply uses that same speaker path, so the microphone treats it as the rover's own voice.
- [ ] Quiet hours: "be quiet" sets listening to commands only, or pauses the chat model, until "you can talk". Commands still work. `set_listening` remains the ROS switch for dropping audio entirely.

## Machine sound

The microphone health check (`audio/health.py`) only says whether the stream is dead, clipped, or silent. It does not say whether the rover is failing.

This milestone is the other use of the array: listen to the rover itself, and raise `/diagnostics` when a machine on it stops sounding like a healthy rover. The array hears airborne noise (motors, fans, wheels, a loose panel). It does not hear current, temperature, or a bearing inside a housing. Those stay on their own sensors. A sound fault is a clue, not the only alarm, and it is not an emergency stop.

- [ ] Record a healthy baseline on the rover, in known states the controller already publishes: idle, driving straight, turning. A few minutes each, array mounted where it will stay. Store the spectra on the robot. A baseline from the bench does not transfer.
- [ ] Compare only while nobody is speaking and the rover's voice is not playing. Person speech and "Okay, follow." are not machine faults. Direction helps: sound from the chassis, not from a person standing ahead.
- [ ] Compare inside one motion state. Driving is louder than idle. A fault is "this drive does not match the healthy drive," not "this is louder than silence."
- [ ] Publish a second diagnostics status, separate from the voice-input status. OK when the spectrum stays near the baseline. WARN when it drifts. ERROR when it stays far for several seconds. Include which state was compared. Do not name a part (motor, fan, wheel) until a recording of that failure exists.
- [ ] Say a fixed sentence on the change, once, not every second: "Something sounds wrong." The chat model does not invent the fault.
- [ ] When a known-bad recording exists (a dry bearing, a rubbing wheel), add that label. Until then the message stays "does not match the healthy recording."

## Software health by voice

The spoken side can report whether software is up, and it can run a few fixed actions. The chat model does not choose the action and it does not get a shell. A listed phrase runs an allowlisted check. The model may speak the result in one sentence. Motion commands stay on the grammar path. "Follow" is not a recovery action.

- [ ] A reader with no model in it. On ROS: node list, whether `/rover_voice` is publishing, `/diagnostics` level, and a heartbeat newer than a few seconds. Off ROS: the voice process, the speech model loaded, the microphone open. The result is a struct, not a paragraph.
- [ ] Spoken phrases for that struct, tested like commands: "what's down", "are you up", "status". The reply names only what the reader returned. If the reader found nothing wrong, say so. The model does not add a fault.
- [ ] An allowlist of actions, each a phrase: "restart voice", "start listening", "stop listening". `set_listening` is already the pause. Restart means the launch respawn this node already does, or a named service call that is written down in the repo. Anything not on the list is chat, not a command.
- [ ] The model can explain a result it was given ("the microphone node is not publishing"). It cannot invent `ros2` commands, package names, or a restart. A test feeds it a down node and checks the spoken line does not claim the rover is moving.
- [ ] If the voice node itself is the thing that is down, this node cannot say so. A second, tiny watchdog outside the voice process has to notice and restart it. Document that limit next to the launch respawn.

## Talking the way earbuds do

AirPods are not a rover interface. The part worth copying is how they behave while someone is speaking. They detect the wearer's voice, duck whatever they were playing, and answer in one short line without a screen. The H2 does that with a jaw accelerometer and an always-on wake word. This rover has a microphone array and, later, a camera. It does not have a jaw sensor.

- [ ] Ducking is the barge-in that already exists. A person starting to speak stops the rover's sentence. Keep that for chat and for commands. Measure that the rest of the sentence does not get transcribed as the next command.
- [ ] "Are you talking to me" is the jaw accelerometer. Use the array direction first: speech from the front is address, speech from the side is ignored for chat. Add a camera only after that is tried. A face toward the rover plus speech is address. A face turned away is not. Gestures do not replace Follow, Stay, Fetch, Come, or Give.
- [ ] Show the heard words. A small display, or a ROS image the operator already watches, prints the transcript and the command as they happen. The astronaut still does not need the screen. The operator uses it when the speaker is hard to hear.
- [ ] One short spoken answer, then stop. No list read aloud. The heard-lamp from the later features covers the case where they cannot hear the reply.

## Possible later features

Not scheduled. Each one stays off the command decision unless it says otherwise.

- [ ] Recognition reply, then a motion reply. "Okay, follow." means the words were accepted. "Moving." or "I can't." is spoken only after the controller publishes a result. Until that topic exists, keep the short recognition line.
- [ ] A heard-indicator. A lamp or a short tone on speech start and on `CommandAccepted`, because the astronaut may not hear the speaker. The Flex board has no LEDs for this.
- [ ] An accuracy session with people. Five people read [commands.md](commands.md), then say the same intents in their own words, on the Mac and again on the rover with the motors on. Record time to `CommandAccepted`, wrong command, and missed command.
- [ ] Replay `logs/*.jsonl` through the session with no microphone and no Whisper, so a phrase change fails in `scripts/test` when it steals or drops a command.
- [ ] Stamp `command` and `utterance` from the ROS clock. `started_at` is the computer's wall clock today.
- [ ] Publish `Clarify` and `Ignored` as their own topics. A controller that only hears `command` cannot tell silence from a refused line.
- [ ] A steadier offline voice for chat and status. `say` and espeak stay enough for "Okay, stay."
- [ ] An optional "say Rover first" mode. The name is optional today. Turn it on only after the direction filter has been tried. Requiring the name misses short commands.

Speech is not the emergency stop. "Stop" is Stay. A hardware or controller stop has to work when the microphone, the USB link, or Whisper does not.

## Not in this repo

Motion, follow distance, the stay lock, grasping, and placing the hammer belong to the controller. Speech only reports the command and, when the array is calibrated, the direction. Chat can talk about that state. It does not act on it.
