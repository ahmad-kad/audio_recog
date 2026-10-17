"""Session output for commands and chat without a model."""

from rover_voice.session import RoverSession


def _session() -> RoverSession:
    return RoverSession(speak=False, use_llm=False, log_dir=None)


def test_follow_prints_success(capsys):
    session = _session()
    assert session.handle_text("follow") is True
    output = capsys.readouterr().out
    assert "SUCCESS: FOLLOW" in output
    assert "ROVER: Okay, follow." in output
    assert "COMMAND: FOLLOW" in output
    assert session.state.command == "FOLLOW"


def test_each_task_command_is_reported(capsys):
    session = _session()
    for text, name in (
        ("stay where you are", "STAY"),
        ("fetch the rock pick hammer", "FETCH"),
        ("come here", "COME"),
        ("place it on the ground", "GIVE"),
    ):
        session.handle_text(text)
        assert session.state.command == name
    output = capsys.readouterr().out
    assert "SUCCESS: STAY" in output
    assert "SUCCESS: FETCH" in output
    assert "object=rock_pick_hammer" in output
    assert "SUCCESS: COME" in output
    assert "SUCCESS: GIVE" in output
    assert "REJECTED" not in output


def test_chat_does_not_print_success(capsys):
    session = _session()
    session.handle_text("what time is it?")
    output = capsys.readouterr().out
    assert "SUCCESS" not in output
    assert "ROVER: I can follow, stay, fetch, come, or give." in output
    assert session.state.command == "none"


def test_ambiguous_speech_asks_for_clarification(capsys):
    session = _session()
    session.handle_text("follow come here")
    output = capsys.readouterr().out
    assert "CLARIFY:" in output
    assert "I did not understand" in output
    assert session.state.command == "none"


def test_goodbye_ends_the_session(capsys):
    session = _session()
    assert session.handle_text("goodbye") is False
    assert "Signing off." in capsys.readouterr().out
