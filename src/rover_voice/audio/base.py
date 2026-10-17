"""Microphone interface shared by the Mac input and the reSpeaker bridge."""

from typing import Protocol

import numpy as np

from rover_voice.audio.direction import DirectionSource


class Microphone(Protocol):
    sample_rate: int
    frame_samples: int

    @property
    def directions(self) -> DirectionSource | None:
        """Direction of speech, or None when the input cannot tell."""

    def start(self, device: str | int | None = None) -> str:
        """Open the input. Return a name to show the user."""

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        """Next mono float32 frame, or None if nothing arrived in time."""

    def drain(self) -> None:
        """Drop frames that are already queued."""

    def close(self) -> None: ...
