"""Watch the microphone stream for faults a person can act on.

Silence, clipping, and a dead stream are reported here. The ROS node copies
the same report onto /diagnostics. The voice loop keeps running.
"""

import threading
import time
from dataclasses import dataclass

import numpy as np

from rover_voice.config import SAMPLE_RATE

# Digital silence, not a quiet room. A muted input sits near zero.
_QUIET_RMS = 1e-4
_QUIET_S = 3.0
_CLIP_PEAK = 0.98
_CLIP_FRAMES = 5
# Same order as the bridge stall timeout.
_GAP_S = 2.0


@dataclass(frozen=True)
class AudioReport:
    level: str
    message: str
    rms: float
    peak: float


class AudioMonitor:
    """Thread-safe view of the latest audio frames."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        now = time.monotonic()
        self._opened_at = now
        self._last_frame_at = now
        self._saw_frame = False
        self._rms = 0.0
        self._peak = 0.0
        self._clip_frames = 0
        self._quiet_s = 0.0
        self._stalled = False

    def observe(self, frame: np.ndarray | None) -> None:
        """Record one captured frame. None means the read timed out."""
        if frame is None:
            return
        samples = np.asarray(frame, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples * samples) + 1e-12))
        with self._lock:
            self._saw_frame = True
            self._last_frame_at = time.monotonic()
            self._peak = peak
            self._rms = rms
            if peak >= _CLIP_PEAK:
                self._clip_frames += 1
            else:
                self._clip_frames = 0
            if rms < _QUIET_RMS:
                self._quiet_s += samples.size / SAMPLE_RATE
            else:
                self._quiet_s = 0.0

    def set_stalled(self, stalled: bool) -> None:
        """The bridge is open but has stopped sending audio."""
        with self._lock:
            self._stalled = stalled

    def report(self) -> AudioReport:
        now = time.monotonic()
        with self._lock:
            rms, peak = self._rms, self._peak
            if self._stalled:
                return AudioReport("error", "No audio from the reSpeaker.", rms, peak)
            gap = now - (self._last_frame_at if self._saw_frame else self._opened_at)
            if gap >= _GAP_S:
                return AudioReport("error", "No audio frames.", rms, peak)
            if self._clip_frames >= _CLIP_FRAMES:
                return AudioReport("error", "Audio is clipping.", rms, peak)
            if self._quiet_s >= _QUIET_S:
                return AudioReport("warn", "Audio level is near silence.", rms, peak)
            return AudioReport("ok", "Audio ok.", rms, peak)
