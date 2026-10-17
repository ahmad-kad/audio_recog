"""Recognized speech becomes a command name, without rover behavior."""

import pytest

from rover_voice.nlu.parser import CommandParser, Intent
from rover_voice.rover.arbiter import CommandArbiter, RoverState


def _decide(text: str, state: RoverState | None = None):
    parsed = CommandParser().parse(text)
    return CommandArbiter().decide(parsed, state or RoverState())


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("follow", Intent.FOLLOW),
        ("stay", Intent.STAY),
        ("fetch the tool", Intent.FETCH),
        ("come", Intent.COME),
        ("give", Intent.GIVE),
        ("drop the hammer", Intent.GIVE),
        ("place it on the ground", Intent.GIVE),
    ],
)
def test_task_phrases_are_commands(text, intent):
    decision = _decide(text)
    assert decision.status == "approved"
    assert decision.intent is intent
    assert decision.action == intent.value
    assert decision.speech == f"Okay, {intent.value.lower()}."


def test_commands_do_not_depend_on_previous_commands():
    state = RoverState()
    first = _decide("fetch the hammer", state)
    state.apply(first.intent)
    second = _decide("fetch", state)
    third = _decide("give", state)
    assert first.status == "approved"
    assert second.status == "approved"
    assert third.status == "approved"
    assert state.command == "FETCH"


def test_unclear_command_does_not_approve():
    decision = _decide("follow come here")
    assert decision.status == "clarify"
    assert decision.speech.startswith("I did not understand")
