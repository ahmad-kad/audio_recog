"""Requests from another thread are applied by the voice loop."""

import threading

from rover_voice.control import LoopControl, Say, SetListening, TextInput
from rover_voice.events import CommandAccepted, EventBus, Reply, Status
from rover_voice.runtime import run_headless
from rover_voice.session import RoverSession
from tests.test_events import _QuietSpeaker


def _session(**kwargs) -> tuple[RoverSession, list, _QuietSpeaker]:
    seen: list = []
    speaker = _QuietSpeaker()
    session = RoverSession(
        use_llm=False, log_dir=None, events=EventBus(seen.append), speaker=speaker, **kwargs
    )
    return session, seen, speaker


def test_say_speaks_and_reports_a_reply():
    session, seen, speaker = _session()
    control = LoopControl()
    control.submit(Say("Battery low."))
    assert control.apply(session)
    assert speaker.spoken == ["Battery low."]
    assert Reply("Battery low.") in seen


def test_text_input_runs_the_command_path():
    session, seen, _ = _session()
    control = LoopControl()
    control.submit(TextInput("follow me"))
    control.apply(session)
    assert any(isinstance(e, CommandAccepted) and e.intent == "FOLLOW" for e in seen)


def test_listening_can_be_paused_and_resumed():
    session, seen, _ = _session()
    control = LoopControl()
    control.submit(SetListening(False))
    control.apply(session)
    assert control.listening is False
    assert Status("Listening paused.") in seen
    control.submit(SetListening(True))
    control.apply(session)
    assert control.listening is True


def test_service_mode_does_not_quit_on_goodbye():
    session, _, _ = _session(allow_quit=False)
    assert session.handle_text("goodbye") is True


def test_headless_loop_stops_on_request():
    session, seen, _ = _session()
    control = LoopControl()
    control.submit(TextInput("stay"))
    timer = threading.Timer(0.2, control.stop)
    timer.start()
    assert run_headless(session, control) == 0
    assert any(isinstance(e, CommandAccepted) and e.intent == "STAY" for e in seen)
