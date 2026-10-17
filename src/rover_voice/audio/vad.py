"""Energy voice-activity detector that cuts utterances out of a live mic stream."""

from collections import deque
from dataclasses import dataclass

import numpy as np

from rover_voice.config import (
    ENDPOINT_SILENCE_S,
    FRAME_MS,
    MAX_UTTERANCE_S,
    MIN_RMS_THRESHOLD,
    MIN_SPEECH_S,
    SAMPLE_RATE,
    SPEECH_START_FRAMES,
    SPEECH_THRESHOLD_MULTIPLIER,
)


@dataclass(frozen=True)
class FeedResult:
    event: str
    audio: np.ndarray | None = None


class UtteranceSegmenter:
    """Turn 30 ms frames into one utterance after a short silence."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        frame_ms: int = FRAME_MS,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self._noise_rms = MIN_RMS_THRESHOLD
        self._calibrated = False
        self._calibration: list[float] = []
        self._preroll: deque[np.ndarray] = deque(maxlen=6)
        self._stored: list[tuple[np.ndarray, bool]] = []
        self._in_speech = False
        self._speech_run = 0
        self._silence_samples = 0
        self.last_rms = 0.0
        self.threshold = MIN_RMS_THRESHOLD

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    @property
    def speech_s(self) -> float:
        samples = sum(len(chunk) for chunk, speech in self._stored if speech)
        return samples / self.sample_rate

    @property
    def trailing_silence_s(self) -> float:
        if not self._in_speech:
            return 0.0
        return self._silence_samples / self.sample_rate

    def preview(self) -> np.ndarray:
        """Audio collected so far. Does not end the utterance."""
        if not self._stored:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate([chunk for chunk, _ in self._stored])
        return np.ascontiguousarray(audio, dtype=np.float32)

    def reset(self) -> None:
        """Drop the open utterance. Keep the learned noise floor."""
        self._stored = []
        self._in_speech = False
        self._speech_run = 0
        self._silence_samples = 0

    def feed(self, frame: np.ndarray) -> FeedResult:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if frame.size == 0:
            return FeedResult("none")

        rms = float(np.sqrt(np.mean(frame * frame) + 1e-12))
        self.last_rms = rms
        if not self._calibrated:
            self._calibration.append(rms)
            self._preroll.append(frame)
            if len(self._calibration) >= 15:
                self._noise_rms = float(np.median(self._calibration))
                self._calibrated = True
            return FeedResult("none")

        self.threshold = max(
            self._noise_rms * SPEECH_THRESHOLD_MULTIPLIER, MIN_RMS_THRESHOLD
        )
        is_speech = rms >= self.threshold
        if not is_speech and rms < self.threshold * 0.8:
            self._noise_rms = (0.95 * self._noise_rms) + (0.05 * rms)

        if not self._in_speech:
            self._preroll.append(frame)
            self._speech_run = self._speech_run + 1 if is_speech else 0
            if self._speech_run >= SPEECH_START_FRAMES:
                self._begin_speech()
                return FeedResult("speech_start")
            return FeedResult("none")

        self._stored.append((frame, is_speech))
        if is_speech:
            self._silence_samples = 0
        else:
            self._silence_samples += int(frame.size)

        total_samples = sum(len(chunk) for chunk, _ in self._stored)
        finished = (
            self._silence_samples >= int(ENDPOINT_SILENCE_S * self.sample_rate)
            or total_samples >= int(MAX_UTTERANCE_S * self.sample_rate)
        )
        if not finished:
            return FeedResult("none")
        return self._finish()

    def _begin_speech(self) -> None:
        preroll = list(self._preroll)
        flags = [False] * len(preroll)
        for index in range(1, min(SPEECH_START_FRAMES, len(preroll)) + 1):
            flags[-index] = True
        self._stored = list(zip(preroll, flags))
        self._in_speech = True
        self._silence_samples = 0

    def _finish(self) -> FeedResult:
        speech_samples = sum(len(chunk) for chunk, speech in self._stored if speech)
        silence_samples = self._silence_samples
        audio = (
            np.concatenate([chunk for chunk, _ in self._stored])
            if self._stored
            else np.zeros(0, dtype=np.float32)
        )
        self.reset()
        keep = int(0.2 * self.sample_rate)
        if silence_samples > keep and audio.size > silence_samples:
            audio = audio[: -(silence_samples - keep)]
        if speech_samples < int(MIN_SPEECH_S * self.sample_rate) or audio.size == 0:
            return FeedResult("none")
        return FeedResult("utterance", np.ascontiguousarray(audio, dtype=np.float32))
