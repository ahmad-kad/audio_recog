"""Hardware check, live direction view, and calibration for the reSpeaker Flex."""

import subprocess
import time

import numpy as np

from rover_voice.audio.direction import (
    CALIBRATION_PATH,
    Calibration,
    arrow,
    now,
    side_name,
)
from rover_voice.audio.serial_capture import SerialMicrophoneStream
from rover_voice.config import ON_MAC
from rover_voice.errors import AudioDeviceError
from rover_voice.tts import create_speaker

_WINDOW_S = 0.6
_CAPTURE_S = 4.0
_MOVE_S = 4.0
_BEEP = "/System/Library/Sounds/Tink.aiff"


def _open(device: str) -> SerialMicrophoneStream | None:
    microphone = SerialMicrophoneStream()
    try:
        print(f"Microphone: {microphone.start(device)}")
    except AudioDeviceError as exc:
        print(exc)
        return None
    return microphone


def run_array_check(device: str, seconds: float = 3.0) -> int:
    """Confirm the bridge streams real-time audio and direction frames."""
    microphone = _open(device)
    if microphone is None:
        return 1
    time.sleep(0.3)
    microphone.drain()
    frames = []
    start = now()
    try:
        while now() - start < seconds:
            frame = microphone.read(timeout=0.5)
            if frame is not None:
                frames.append(frame)
    finally:
        microphone.close()
    directions = microphone.directions.samples_since(start)

    audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
    audio_s = audio.size / microphone.sample_rate
    rms = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0
    checks = [
        (
            "audio arrives in real time",
            abs(audio_s - seconds) <= 0.25,
            f"{audio_s:.2f} s of audio in {seconds:.0f} s",
        ),
        (
            "audio is not noise or silence",
            1e-5 < rms < 0.1,
            f"RMS {rms:.4f}, a quiet room is about 0.003 to 0.01",
        ),
        (
            "direction frames arrive",
            len(directions) >= 5 * seconds,
            f"{len(directions) / seconds:.0f} per second",
        ),
    ]
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name} ({detail})")
    if not checks[1][1]:
        print("Loud noise-like audio usually means the I2S format does not match the XVF3800 firmware.")
    return 0 if all(ok for _, ok, _ in checks) else 1


def run_doa_monitor(device: str) -> int:
    microphone = _open(device)
    if microphone is None:
        return 1
    tracker = microphone.directions
    if tracker.calibration is None:
        print("Not calibrated yet: angles are the board's own. Run --doa-calibrate.")
    print("Talk from different sides. Ctrl-C to quit.")
    try:
        while True:
            microphone.read(timeout=0.1)
            board = tracker.board_degrees_since(now() - _WINDOW_S)
            if board is None:
                line = "  (quiet)"
            elif tracker.calibration is None:
                line = f"  speech at {board:3.0f}° on the board"
            else:
                rover = tracker.calibration.to_rover(board)
                line = f"  {arrow(rover)} {side_name(rover):<11} {rover:3.0f}°   (board {board:3.0f}°)"
            print(f"\r{line:<50}", end="", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        microphone.close()
    return 0


def _say(text: str, show: bool = True) -> None:
    if show:
        print(text)
    speaker = create_speaker()
    speaker.speak(text)
    speaker.wait()


def _beep() -> None:
    if ON_MAC:
        subprocess.run(["afplay", _BEEP])
    else:
        _say("Now.", show=False)


def _capture_angle(microphone: SerialMicrophoneStream, where: str) -> float | None:
    # Spoken prompts, so no keyboard is needed next to the rover.
    _say(f"Stand at the rover's {where}, about a meter away. Talk after the beep.")
    time.sleep(_MOVE_S)
    _beep()
    print(f"  talk now for {_CAPTURE_S:.0f} seconds...")
    start = now()
    while now() - start < _CAPTURE_S:
        microphone.read(timeout=0.1)
    angle = microphone.directions.board_degrees_since(start)
    _beep()
    if angle is None:
        _say("I did not hear you. Let's try that again, louder.")
    else:
        print(f"  heard at {angle:.0f}° on the board")
    return angle


def _capture_speaker(microphone: SerialMicrophoneStream) -> float | None:
    _say("Now stay quiet. The rover will talk through its speaker.")
    time.sleep(1.0)
    microphone.drain()
    start = now()
    _say("Calibrating the rover speaker. One, two, three, four, five.", show=False)
    microphone.read(timeout=0.3)
    angle = microphone.directions.board_degrees_since(start)
    if angle is None:
        print("  The array did not hear the speaker (headphones?). Its voice will")
        print("  be filtered by text only.")
    else:
        print(f"  speaker heard at {angle:.0f}° on the board")
    return angle


def run_doa_calibrate(device: str) -> int:
    microphone = _open(device)
    if microphone is None:
        return 1
    time.sleep(0.5)
    try:
        front = None
        while front is None:
            front = _capture_angle(microphone, "front")
        right = None
        while right is None:
            right = _capture_angle(microphone, "right side")
        speaker = _capture_speaker(microphone)
    except (KeyboardInterrupt, EOFError):
        print("\nCalibration cancelled.")
        return 1
    finally:
        microphone.close()

    turn = (right - front) % 360.0
    if not (45.0 <= turn <= 135.0 or 225.0 <= turn <= 315.0):
        print(
            f"Front and right are {turn:.0f}° apart, expected about 90°. "
            "Stand further from the board, keep the room quiet, and run it again."
        )
        return 1
    calibration = Calibration(
        front_degrees=front, clockwise=turn < 180.0, speaker_degrees=speaker
    )
    calibration.save()
    print(f"Saved to {CALIBRATION_PATH}: front is {front:.0f}° on the board.")
    _say("Calibration saved.")
    return 0
