"""The session reports through events; views turn them into text or JSON."""

import io
import json

from rover_voice.events import (
    CommandAccepted,
    ConsoleView,
    EventBus,
    Heard,
    JsonView,
    Reply,
    SessionEnded,
    StateChanged,
)
from rover_voice.session import RoverSession


class _QuietSpeaker:
    enabled = False
    busy = False

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def interrupt(self) -> None:
        pass

    def wait(self) -> None:
        pass

    def poll(self) -> None:
        pass

    def echoing(self, grace_s: float = 0.12) -> bool:
        return False


def _session() -> tuple[RoverSession, list, _QuietSpeaker]:
    seen: list = []
    speaker = _QuietSpeaker()
    session = RoverSession(
        use_llm=False, log_dir=None, events=EventBus(seen.append), speaker=speaker
    )
    return session, seen, speaker


def test_command_emits_heard_accepted_reply_and_state():
    session, seen, speaker = _session()
    session.handle_text("follow me", asr_ms=120.0, direction="→ right (90°)")
    assert [type(e) for e in seen] == [Heard, CommandAccepted, Reply, StateChanged]
    accepted = seen[1]
    assert accepted.intent == "FOLLOW"
    assert accepted.direction == "→ right (90°)"
    assert speaker.spoken == ["Okay, follow."]


def test_quit_ends_with_session_ended():
    session, seen, _ = _session()
    assert session.handle_text("goodbye") is False
    assert isinstance(seen[-1], SessionEnded)


def test_json_view_writes_one_object_per_event():
    out = io.StringIO()
    view = JsonView(out)
    view(CommandAccepted("FETCH", 0.96, slots={"object": "rock_pick_hammer"}))
    view(SessionEnded())
    records = [json.loads(line) for line in out.getvalue().splitlines()]
    assert records[0]["event"] == "CommandAccepted"
    assert records[0]["slots"] == {"object": "rock_pick_hammer"}
    assert records[1] == {"event": "SessionEnded"}


def test_console_view_keeps_the_terminal_lines():
    fmt = ConsoleView.format
    assert fmt(Heard("heel", 113.0, "→ right (90°)")) == (
        "FROM: → right (90°)\nYOU: heel\nASR: 113 ms"
    )
    assert fmt(CommandAccepted("FOLLOW", 0.83, by_meaning=True)) == (
        "SUCCESS: FOLLOW (confidence 0.83) by meaning"
    )
    assert fmt(StateChanged("FOLLOW")) == "COMMAND: FOLLOW"
    assert fmt(SessionEnded()) is None
