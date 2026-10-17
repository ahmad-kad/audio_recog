"""Parser coverage for the five rover commands and their paraphrases."""

import pytest

from rover_voice.nlu.parser import CommandParser, Intent

parser = CommandParser()


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Follow me", Intent.FOLLOW),
        ("follow", Intent.FOLLOW),
        ("Come with me", Intent.FOLLOW),
        ("Track me", Intent.FOLLOW),
        ("Could you follow me over there?", Intent.FOLLOW),
        ("Stay", Intent.STAY),
        ("stay where you are", Intent.STAY),
        ("Wait here", Intent.STAY),
        ("Hold position", Intent.STAY),
        ("Wait, stay there.", Intent.STAY),
        ("stop", Intent.STAY),
        ("stop there", Intent.STAY),
        ("stop right there", Intent.STAY),
        ("Stop here", Intent.STAY),
        ("Fetch the hammer", Intent.FETCH),
        ("fetch the tool", Intent.FETCH),
        ("fetch the rock pick hammer", Intent.FETCH),
        ("Get the tool", Intent.FETCH),
        ("Go get that hammer.", Intent.FETCH),
        ("Come here", Intent.COME),
        ("Come to me", Intent.COME),
        ("come", Intent.COME),
        ("over here", Intent.COME),
        ("right over here", Intent.COME),
        ("come over here", Intent.COME),
        ("get over here", Intent.COME),
        ("walk with me", Intent.FOLLOW),
        ("stick with me", Intent.FOLLOW),
        ("keep up with me", Intent.FOLLOW),
        ("do not move", Intent.STAY),
        ("stand still", Intent.STAY),
        ("stop right here", Intent.STAY),
        ("bring me the hammer", Intent.FETCH),
        ("retrieve the tool", Intent.FETCH),
        ("this way", Intent.COME),
        ("come closer", Intent.COME),
        ("head over here", Intent.COME),
        ("let go", Intent.GIVE),
        ("hand me the hammer", Intent.GIVE),
        ("release the hammer", Intent.GIVE),
        ("drop", Intent.GIVE),
        ("Give", Intent.GIVE),
        ("Put it down", Intent.GIVE),
        ("place it on the ground", Intent.GIVE),
        ("Drop the hammer", Intent.GIVE),
        ("heel", Intent.FOLLOW),
        ("by my side", Intent.FOLLOW),
        ("sit", Intent.STAY),
        ("sit down", Intent.STAY),
        ("here", Intent.COME),
        ("heal", Intent.FOLLOW),
        ("he'll", Intent.FOLLOW),
        ("hear", Intent.COME),
        ("over hear", Intent.COME),
        ("weight", Intent.STAY),
    ],
)
def test_spec_commands(text, intent):
    result = parser.parse(text)
    assert result.kind == "command"
    assert result.intent is intent
    assert result.confidence >= 0.82


def test_fetch_slot_is_the_hammer():
    result = parser.parse("Go get that hammer.")
    assert result.slots["object"] == "rock_pick_hammer"


def test_come_with_me_is_follow_not_come():
    result = parser.parse("Come with me")
    assert result.intent is Intent.FOLLOW


def test_come_here_is_not_follow():
    result = parser.parse("Come here")
    assert result.intent is Intent.COME


def test_expanded_phrases_keep_their_meanings():
    assert parser.parse("follow me this way").intent is Intent.FOLLOW
    assert parser.parse("come with me").intent is Intent.FOLLOW
    assert parser.parse("stay right here").intent is Intent.STAY
    assert parser.parse("give me the hammer").intent is Intent.GIVE
    assert parser.parse("bring me the hammer").intent is Intent.FETCH
    assert parser.parse("set it down").intent is Intent.GIVE
    assert parser.parse("I hear you").kind == "chat"
    assert parser.parse("let go").intent is Intent.GIVE
    assert parser.parse("put it down").intent is Intent.GIVE
    assert parser.parse("place the hammer").intent is Intent.GIVE
    assert parser.parse("stay here").intent is Intent.STAY
    assert parser.parse("come here").intent is Intent.COME


def test_vague_words_are_not_commands():
    for text in (
        "down",
        "set",
        "place",
        "out",
        "let's go",
        "leave it",
        "get it",
        "bring it",
        "follow the instructions",
        "what the hell",
    ):
        result = parser.parse(text)
        assert result.kind == "chat", text


def test_dont_follow_is_stay():
    for text in ("dont follow", "don't follow me", "stop following me"):
        result = parser.parse(text)
        assert result.kind == "command", text
        assert result.intent is Intent.STAY


def test_typo_still_matches_follow():
    result = parser.parse("folow me")
    assert result.kind == "command"
    assert result.intent is Intent.FOLLOW


def test_give_me_a_second_is_chat():
    result = parser.parse("give me a second")
    assert result.kind == "chat"


def test_ordinary_speech_is_chat():
    result = parser.parse("What time is it?")
    assert result.kind == "chat"
    assert result.intent is None


def test_two_commands_ask_for_clarification():
    result = parser.parse("follow come here")
    assert result.kind == "clarify"
    assert result.confidence > 0


def test_stop_following_is_stay():
    result = parser.parse("stop following me")
    assert result.kind == "command"
    assert result.intent is Intent.STAY
