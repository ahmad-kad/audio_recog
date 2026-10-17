"""What the voice loop reports, as typed events.

The session and the live loop emit events instead of printing. A listener
decides what to do with them: ConsoleView prints the familiar terminal
lines, JsonView writes one JSON object per line for a rover controller, and
a test can collect them in a list.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable, TextIO


@dataclass(frozen=True)
class Status:
    """Progress and state messages: loading, listening, speech detected."""

    message: str


@dataclass(frozen=True)
class Heard:
    """A transcript.

    direction is a label for people. direction_deg is the rover angle,
    clockwise from the front (90 is right); it is set only once the array is
    calibrated. started_at is the wall-clock time speech began.
    """

    text: str
    asr_ms: float | None = None
    direction: str | None = None
    direction_deg: float | None = None
    started_at: float | None = None


@dataclass(frozen=True)
class CommandAccepted:
    """A command was recognized. A rover controller acts on this."""

    intent: str
    confidence: float
    by_meaning: bool = False
    slots: dict[str, str] = field(default_factory=dict)
    direction: str | None = None
    direction_deg: float | None = None
    started_at: float | None = None
    text: str = ""


@dataclass(frozen=True)
class CommandRejected:
    intent: str
    reason: str


@dataclass(frozen=True)
class Clarify:
    confidence: float | None = None


@dataclass(frozen=True)
class Reply:
    """What the rover says."""

    speech: str
    llm_ms: float | None = None


@dataclass(frozen=True)
class StateChanged:
    command: str


@dataclass(frozen=True)
class Ignored:
    """Sound that was heard but not acted on, and why."""

    reason: str


@dataclass(frozen=True)
class SessionEnded:
    pass


Event = (
    Status
    | Heard
    | CommandAccepted
    | CommandRejected
    | Clarify
    | Reply
    | StateChanged
    | Ignored
    | SessionEnded
)
Listener = Callable[[Event], None]


class EventBus:
    """Deliver each event to every listener, in subscription order."""

    def __init__(self, *listeners: Listener) -> None:
        self._listeners: list[Listener] = list(listeners)

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def emit(self, event: Event) -> None:
        for listener in self._listeners:
            listener(event)


class ConsoleView:
    """Print events as the terminal lines the prototype has always shown."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def __call__(self, event: Event) -> None:
        line = self.format(event)
        if line is not None:
            print(line, file=self._stream or sys.stdout, flush=True)

    @staticmethod
    def format(event: Event) -> str | None:
        match event:
            case Status(message):
                return message
            case Heard(text, asr_ms, direction, _, _):
                lines = []
                if direction:
                    lines.append(f"FROM: {direction}")
                lines.append(f"YOU: {text}")
                if asr_ms is not None:
                    lines.append(f"ASR: {asr_ms:.0f} ms")
                return "\n".join(lines)
            case CommandAccepted(intent, confidence, by_meaning, slots):
                how = " by meaning" if by_meaning else ""
                extra = "".join(f" {key}={value}" for key, value in slots.items())
                return f"SUCCESS: {intent} (confidence {confidence:.2f}){how}{extra}"
            case CommandRejected(intent, reason):
                return f"REJECTED: {intent} ({reason})"
            case Clarify(confidence):
                if confidence is None:
                    return "CLARIFY: (no transcript)"
                return f"CLARIFY: (confidence {confidence:.2f})"
            case Reply(speech, llm_ms):
                if llm_ms is None:
                    return f"ROVER: {speech}"
                return f"ROVER: {speech}  [llm {llm_ms:.0f} ms]"
            case StateChanged(command):
                return f"COMMAND: {command}"
            case Ignored(reason):
                return f"Ignored: {reason}"
            case SessionEnded():
                return None
        return None


class JsonView:
    """One JSON object per line: {"event": "CommandAccepted", ...fields}."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def __call__(self, event: Event) -> None:
        print(to_json(event), file=self._stream or sys.stdout, flush=True)


def to_json(event: Event) -> str:
    return json.dumps({"event": type(event).__name__, **asdict(event)})


def console_bus() -> EventBus:
    return EventBus(ConsoleView())
