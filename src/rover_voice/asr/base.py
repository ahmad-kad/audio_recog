"""Speech-recognition backend interface.

The Mac uses MLX Whisper and Linux uses faster-whisper. Another backend
only has to implement these two methods.
"""

from typing import Protocol

import numpy as np

from rover_voice.config import SAMPLE_RATE


class ASRBackend(Protocol):
    model_id: str

    def warmup(self) -> None:
        """Load the model now, so the first command is not slow."""

    def transcribe(self, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        """Return the transcript for one clip of 16 kHz mono float32 audio."""


def prepare_audio(audio: np.ndarray) -> np.ndarray:
    """Flatten to float32 and apply mild gain. Empty for near silence."""
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak < 1e-4:
        return np.zeros(0, dtype=np.float32)
    # Mild automatic gain so a quiet microphone still reaches Whisper.
    samples = np.clip(samples * min(0.9 / peak, 6.0), -1.0, 1.0)
    return np.ascontiguousarray(samples, dtype=np.float32)


def warmup_tone() -> np.ndarray:
    """One second of tone. Silence is dropped by the gain stage and would
    not make a backend load anything."""
    time_axis = np.arange(SAMPLE_RATE, dtype=np.float32)
    tone = 0.05 * np.sin(2 * np.pi * 220.0 * time_axis / SAMPLE_RATE)
    return tone.astype(np.float32)
