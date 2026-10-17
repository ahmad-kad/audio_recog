"""Microphone capture for the Mac prototype."""

import queue
from typing import Any

import numpy as np

from rover_voice.audio.base import Microphone
from rover_voice.config import FRAME_MS, SAMPLE_RATE
from rover_voice.errors import AudioDeviceError


def _resolve_input_device(sd, device: str | int | None):
    """Return a sounddevice index, or None for the system default input."""
    if device is None:
        return None
    if isinstance(device, int) or (isinstance(device, str) and device.isdigit()):
        return int(device)
    matches = []
    for index, info in enumerate(sd.query_devices()):
        if info["max_input_channels"] < 1:
            continue
        if device.lower() in str(info["name"]).lower():
            matches.append(index)
    if len(matches) == 1:
        return matches[0]
    names = [
        f"{index}: {info['name']}"
        for index, info in enumerate(sd.query_devices())
        if info["max_input_channels"] > 0
    ]
    raise AudioDeviceError(
        f"Could not choose a microphone from {device!r}. Inputs:\n" + "\n".join(names)
    )


class MicrophoneStream:
    """16 kHz mono frames from the selected input device."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_ms: int = FRAME_MS) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Any = None  # sounddevice.InputStream
        self.directions = None  # a plain microphone cannot tell direction

    def start(self, device: str | int | None = None) -> str:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise AudioDeviceError(
                "sounddevice is not available. Re-run scripts/setup.sh."
            ) from exc

        try:
            selected = _resolve_input_device(sd, device)
            info = sd.query_devices(selected if selected is not None else sd.default.device[0])
            self._stream = sd.InputStream(
                device=selected,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.frame_samples,
                latency="low",
                callback=self._on_audio,
            )
            self._stream.start()
        except AudioDeviceError:
            raise
        except Exception as exc:
            raise AudioDeviceError(
                "Could not open the microphone. Grant microphone access to "
                "this terminal in System Settings, Privacy and Security, "
                "Microphone. Or run with --text to type commands instead."
            ) from exc
        return str(info["name"])

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Drop audio captured while the rover was speaking."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status) -> None:
        del frames, time_info, status
        self._queue.put(np.array(indata[:, 0], dtype=np.float32, copy=True))


def open_microphone(device: str | int | None) -> Microphone:
    """Pick the XIAO serial bridge for xiao or a /dev path, else a Mac input."""
    from rover_voice.audio.serial_capture import SerialMicrophoneStream, is_serial_input

    if is_serial_input(device):
        return SerialMicrophoneStream()
    return MicrophoneStream()
