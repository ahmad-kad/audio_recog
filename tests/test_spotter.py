"""When a partial transcript is allowed to fire."""

from rover_voice.nlu.parser import CommandParser, Intent
from rover_voice.nlu.spotter import spot_command

parser = CommandParser()


def test_clear_command_fires_before_the_pause():
    result = spot_command(parser, "heel", 0.0)
    assert result is not None
    assert result.intent is Intent.FOLLOW

    result = spot_command(parser, "heal", 0.0)
    assert result is not None
    assert result.intent is Intent.FOLLOW

    result = spot_command(parser, "follow me", 0.0)
    assert result is not None
    assert result.intent is Intent.FOLLOW

    result = spot_command(parser, "come with me", 0.0)
    assert result is not None
    assert result.intent is Intent.FOLLOW


def test_words_that_can_change_wait_for_a_short_pause():
    assert spot_command(parser, "come", 0.0) is None
    assert spot_command(parser, "give", 0.0) is None
    assert spot_command(parser, "stop", 0.0) is None
    assert spot_command(parser, "set", 0.0) is None
    assert spot_command(parser, "place", 0.0) is None

    come = spot_command(parser, "come", 0.08)
    assert come is not None and come.intent is Intent.COME
    assert spot_command(parser, "set", 0.08) is None
    assert spot_command(parser, "place", 0.08) is None
    give = spot_command(parser, "give", 0.08)
    assert give is not None and give.intent is Intent.GIVE


def test_a_finished_phrase_does_not_wait():
    result = spot_command(parser, "come here", 0.0)
    assert result is not None
    assert result.intent is Intent.COME
    result = spot_command(parser, "give me the hammer", 0.0)
    assert result is not None
    assert result.intent is Intent.GIVE
    result = spot_command(parser, "set it down", 0.0)
    assert result is not None
    assert result.intent is Intent.GIVE


def test_chat_and_quit_are_not_early_commands():
    assert spot_command(parser, "give me a second", 0.2) is None
    assert spot_command(parser, "what time is it", 0.2) is None
    assert spot_command(parser, "stop listening", 0.2) is None
    assert spot_command(parser, "I hear you", 0.2) is None
