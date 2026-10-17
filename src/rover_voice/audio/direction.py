"""Direction of arrival from the reSpeaker Flex.

The XVF3800 reports an angle in its own frame. Calibration stores which
board angle is the rover's front and whether angles grow to the left or the
right, so a reading can be named "front", "right", and so on. It can also
store where the rover's own speaker is, so its voice can be ignored.
"""

import json
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

# ROVER_DOA_CALIBRATION moves the file, for an installed robot service.
CALIBRATION_PATH = Path(
    os.environ.get(
        "ROVER_DOA_CALIBRATION",
        Path(__file__).resolve().parents[3] / ".doa_calibration.json",
    )
)

_SIDES = (
    "front",
    "front-right",
    "right",
    "back-right",
    "back",
    "back-left",
    "left",
    "front-left",
)


@dataclass(frozen=True)
class DirectionSample:
    time: float
    doa: int | None
    speech: bool
    free_beam: int | None
    auto_beam: int | None
    energy: float


@dataclass(frozen=True)
class Calibration:
    front_degrees: float = 0.0
    clockwise: bool = False
    speaker_degrees: float | None = None

    def to_rover(self, board_degrees: float) -> float:
        """Board angle -> rover angle: 0 front, 90 right, 180 back, 270 left."""
        offset = board_degrees - self.front_degrees
        return (offset if self.clockwise else -offset) % 360.0

    def save(self, path: Path = CALIBRATION_PATH) -> None:
        data = {
            "front_degrees": self.front_degrees,
            "clockwise": self.clockwise,
            "speaker_degrees": self.speaker_degrees,
        }
        path.write_text(json.dumps(data) + "\n")

    @classmethod
    def load(cls, path: Path = CALIBRATION_PATH) -> "Calibration | None":
        try:
            data = json.loads(path.read_text())
            speaker = data.get("speaker_degrees")
            return cls(
                float(data["front_degrees"]),
                bool(data["clockwise"]),
                None if speaker is None else float(speaker),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None


def circular_mean(degrees: Sequence[float]) -> float | None:
    if not degrees:
        return None
    x = sum(math.cos(math.radians(d)) for d in degrees)
    y = sum(math.sin(math.radians(d)) for d in degrees)
    if math.hypot(x, y) < 1e-6:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def angle_gap(a: float, b: float) -> float:
    """Smallest difference between two angles, 0 to 180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def side_name(rover_degrees: float) -> str:
    return _SIDES[int(((rover_degrees + 22.5) % 360.0) // 45.0)]


def arrow(rover_degrees: float) -> str:
    return "↑↗→↘↓↙←↖"[int(((rover_degrees + 22.5) % 360.0) // 45.0)]


DirectionListener = Callable[[DirectionSample], None]


class DirectionSource(Protocol):
    """What the live loop needs to know about where speech came from."""

    calibration: Calibration | None

    def speech_seen_since(self, start: float) -> bool: ...

    def from_speaker_since(self, start: float) -> bool: ...

    def describe_since(self, start: float) -> str | None: ...

    def degrees_since(self, start: float) -> float | None:
        """Rover angle of speech since start, or None if uncalibrated."""

    def subscribe(self, listener: DirectionListener) -> None:
        """Call listener with every new sample, on the reader's thread."""


class DirectionTracker:
    """Recent direction samples, shared between the serial thread and the app."""

    def __init__(self, calibration: Calibration | None = None, keep_s: float = 15.0) -> None:
        self.calibration = calibration
        self._keep_s = keep_s
        self._samples: deque[DirectionSample] = deque()
        self._lock = threading.Lock()
        self._listeners: list[DirectionListener] = []

    def subscribe(self, listener: DirectionListener) -> None:
        self._listeners.append(listener)

    def add(self, sample: DirectionSample) -> None:
        with self._lock:
            self._samples.append(sample)
            while self._samples and sample.time - self._samples[0].time > self._keep_s:
                self._samples.popleft()
        for listener in self._listeners:
            listener(sample)

    def samples_since(self, start: float) -> list[DirectionSample]:
        with self._lock:
            return [s for s in self._samples if s.time >= start]

    def board_degrees_since(self, start: float) -> float | None:
        """Average board angle of speech since start.

        The auto-select beam reacts fastest but points at the loudest noise
        between words, so only beams with speech energy count. DOA_VALUE is
        smoothed and lags a second or more; it is the fallback.
        """
        recent = self.samples_since(start)
        beams = [s.auto_beam for s in recent if s.energy > 0 and s.auto_beam is not None]
        if beams:
            return circular_mean(beams)
        return circular_mean([s.doa for s in recent if s.speech and s.doa is not None])

    def speech_seen_since(self, start: float) -> bool:
        """True once the array reports speech energy on any sample since start.

        The energy rises in the same 60 ms window as the loudness gate and
        falls about 0.1 s after speech, so it adds no delay to commands.
        """
        return any(s.energy > 0 for s in self.samples_since(start))

    def from_speaker_since(self, start: float, tolerance: float = 35.0) -> bool:
        """True when speech since start came from the rover's own speaker."""
        if self.calibration is None or self.calibration.speaker_degrees is None:
            return False
        board = self.board_degrees_since(start)
        if board is None:
            return False
        return angle_gap(board, self.calibration.speaker_degrees) <= tolerance

    def degrees_since(self, start: float) -> float | None:
        board = self.board_degrees_since(start)
        if board is None or self.calibration is None:
            return None
        return self.calibration.to_rover(board)

    def describe_since(self, start: float) -> str | None:
        board = self.board_degrees_since(start)
        if board is None:
            return None
        if self.calibration is None:
            return f"{board:.0f}° on the board (uncalibrated)"
        rover = self.calibration.to_rover(board)
        return f"{arrow(rover)} {side_name(rover)} ({rover:.0f}°)"


def sample_degrees(sample: DirectionSample, calibration: Calibration | None) -> float | None:
    """Rover angle of one sample while it carries speech, else None."""
    if calibration is None or sample.energy <= 0 or sample.auto_beam is None:
        return None
    return calibration.to_rover(sample.auto_beam)


def now() -> float:
    return time.monotonic()


def wall_time(monotonic_time: float) -> float:
    """Convert a time.monotonic() reading to wall-clock seconds."""
    return time.time() - (time.monotonic() - monotonic_time)
