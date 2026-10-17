"""Decide whether a partial transcript is ready to fire.

The grammar parser is the only judge. The meaning model and the chat model
stay off this path so a command can land while the person is still talking.
"""

from rover_voice.config import EARLY_HOLD_SILENCE_S, QUIT_PHRASES
from rover_voice.nlu.parser import (
    CommandParser,
    Intent,
    ParseResult,
    _PHRASES,
    normalize,
)

_GIVE_CHAT_PREFIX = "give me a"


def spot_command(
    parser: CommandParser,
    text: str,
    trailing_silence_s: float,
) -> ParseResult | None:
    """Return a command that is safe to accept before the utterance ends."""
    normalized = normalize(text)
    surface = normalize(text, collapse_bare=False)
    if not normalized or normalized in QUIT_PHRASES:
        return None
    if len(normalized.split()) > 8:
        return None

    parsed = parser.parse(text)
    if parsed.kind != "command" or parsed.intent is None:
        return None
    if _must_wait(surface, parsed.intent) and trailing_silence_s < EARLY_HOLD_SILENCE_S:
        return None
    return parsed


def _must_wait(text: str, intent: Intent) -> bool:
    """True when more words could still change this into another command."""
    if _GIVE_CHAT_PREFIX.startswith(text) or text.startswith(_GIVE_CHAT_PREFIX):
        # "give" can become "give me a second", which is conversation.
        if text == "give" or text.startswith("give me"):
            return True
    for phrase in QUIT_PHRASES:
        if phrase.startswith(text + " "):
            return True
    for phrase, phrase_intent, _score in _PHRASES:
        if phrase.startswith(text + " ") and phrase_intent is not intent:
            return True
    return False
