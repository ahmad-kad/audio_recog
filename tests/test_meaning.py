"""Meaning match for wording that is not a stored phrase."""

import pytest

from rover_voice.nlu.parser import Intent
from rover_voice.nlu.understanding import CommandUnderstanding


@pytest.fixture(scope="module")
def understanding():
    return CommandUnderstanding()


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("please walk alongside me", Intent.FOLLOW),
        ("could you accompany me", Intent.FOLLOW),
        ("come with me", Intent.FOLLOW),
        ("remain right where you are", Intent.STAY),
        ("do not go anywhere", Intent.STAY),
        ("please go pick up that rock pick hammer", Intent.FETCH),
        ("retrieve the rock pick for me", Intent.FETCH),
        ("come on over to my position", Intent.COME),
        ("head this way toward me", Intent.COME),
        ("set that hammer onto the ground", Intent.GIVE),
        ("release the hammer please", Intent.GIVE),
    ],
)
def test_same_meaning_maps_to_the_task(understanding, text, intent):
    result = understanding.interpret(text)
    assert result.kind == "command"
    assert result.intent is intent


@pytest.mark.parametrize(
    "text",
    [
        "good morning",
        "what is your name",
        "give me a second",
        "down",
        "leave it",
        "let's go",
        "get it",
        "out",
    ],
)
def test_unrelated_speech_is_not_a_command(understanding, text):
    result = understanding.interpret(text)
    assert result.kind == "chat"
    assert result.intent is None
