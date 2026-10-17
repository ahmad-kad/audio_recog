"""Deterministic intent parser for the five rover commands.

The chat model never decides whether a command executes. This parser is the
only source of intent, slots, and confidence.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from rover_voice.config import CHAT_THRESHOLD, COMMAND_THRESHOLD


class Intent(Enum):
    FOLLOW = "FOLLOW"
    STAY = "STAY"
    FETCH = "FETCH"
    COME = "COME"
    GIVE = "GIVE"


@dataclass(frozen=True)
class ParseResult:
    kind: str
    intent: Intent | None
    confidence: float
    slots: dict[str, str]
    reason: str


# Longer, more specific phrases outrank a bare keyword via max(), not order.
_PHRASES: tuple[tuple[str, Intent, float], ...] = (
    ("come with me", Intent.FOLLOW, 0.98),
    ("follow me", Intent.FOLLOW, 0.97),
    ("follow behind me", Intent.FOLLOW, 0.97),
    ("walk with me", Intent.FOLLOW, 0.97),
    ("walk behind me", Intent.FOLLOW, 0.96),
    ("keep up with me", Intent.FOLLOW, 0.97),
    ("tag along", Intent.FOLLOW, 0.95),
    ("stick with me", Intent.FOLLOW, 0.96),
    ("shadow me", Intent.FOLLOW, 0.95),
    ("accompany me", Intent.FOLLOW, 0.96),
    ("track me", Intent.FOLLOW, 0.96),
    ("come along", Intent.FOLLOW, 0.94),
    ("follow along", Intent.FOLLOW, 0.94),
    ("stop following", Intent.STAY, 0.98),
    ("dont follow", Intent.STAY, 0.94),
    ("do not move", Intent.STAY, 0.97),
    ("dont move", Intent.STAY, 0.97),
    ("do not go anywhere", Intent.STAY, 0.96),
    ("dont go anywhere", Intent.STAY, 0.96),
    ("hold your position", Intent.STAY, 0.97),
    ("hold position", Intent.STAY, 0.97),
    ("hold still", Intent.STAY, 0.96),
    ("stand still", Intent.STAY, 0.96),
    ("stay still", Intent.STAY, 0.96),
    ("remain here", Intent.STAY, 0.96),
    ("remain there", Intent.STAY, 0.96),
    ("wait right here", Intent.STAY, 0.97),
    ("wait here", Intent.STAY, 0.97),
    ("wait there", Intent.STAY, 0.95),
    ("stay right here", Intent.STAY, 0.97),
    ("stay right there", Intent.STAY, 0.97),
    ("stay there", Intent.STAY, 0.96),
    ("stay here", Intent.STAY, 0.96),
    ("stay put", Intent.STAY, 0.96),
    ("stay where you are", Intent.STAY, 0.97),
    ("stop moving", Intent.STAY, 0.96),
    ("stop right there", Intent.STAY, 0.97),
    ("stop right here", Intent.STAY, 0.97),
    ("stop there", Intent.STAY, 0.96),
    ("stop here", Intent.STAY, 0.96),
    ("stop now", Intent.STAY, 0.95),
    ("head over here", Intent.COME, 0.96),
    ("head over to me", Intent.COME, 0.96),
    ("drive over here", Intent.COME, 0.96),
    ("walk over here", Intent.COME, 0.96),
    ("come to me", Intent.COME, 0.97),
    ("come here", Intent.COME, 0.97),
    ("come over here", Intent.COME, 0.97),
    ("come back here", Intent.COME, 0.96),
    ("come closer", Intent.COME, 0.95),
    ("come this way", Intent.COME, 0.95),
    ("get over here", Intent.COME, 0.96),
    ("right over here", Intent.COME, 0.96),
    ("over this way", Intent.COME, 0.94),
    ("come over", Intent.COME, 0.94),
    ("come back", Intent.COME, 0.94),
    ("over here", Intent.COME, 0.90),
    ("right here", Intent.COME, 0.88),
    ("this way", Intent.COME, 0.88),
    ("approach me", Intent.COME, 0.95),
    ("place the hammer on the ground", Intent.GIVE, 0.97),
    ("place it on the ground", Intent.GIVE, 0.97),
    ("put it on the ground", Intent.GIVE, 0.97),
    ("put the hammer on the ground", Intent.GIVE, 0.97),
    ("put the tool down", Intent.GIVE, 0.96),
    ("set the tool down", Intent.GIVE, 0.96),
    ("set it on the ground", Intent.GIVE, 0.96),
    ("drop the hammer", Intent.GIVE, 0.97),
    ("release the hammer", Intent.GIVE, 0.97),
    ("leave the hammer", Intent.GIVE, 0.95),
    ("hand me the hammer", Intent.GIVE, 0.96),
    ("place the hammer", Intent.GIVE, 0.95),
    ("put the hammer down", Intent.GIVE, 0.96),
    ("put it down", Intent.GIVE, 0.96),
    ("set it down", Intent.GIVE, 0.95),
    ("hand it over", Intent.GIVE, 0.95),
    ("hand it to me", Intent.GIVE, 0.95),
    ("give me the hammer", Intent.GIVE, 0.94),
    ("give it to me", Intent.GIVE, 0.94),
    ("let it go", Intent.GIVE, 0.94),
    ("let go", Intent.GIVE, 0.93),
    ("drop it here", Intent.GIVE, 0.94),
    ("drop it", Intent.GIVE, 0.93),
    ("drop that", Intent.GIVE, 0.92),
    ("release it", Intent.GIVE, 0.92),
    ("give it", Intent.GIVE, 0.92),
    ("by my side", Intent.FOLLOW, 0.96),
    ("beside me", Intent.FOLLOW, 0.95),
    ("sit stay", Intent.STAY, 0.97),
    ("sit down", Intent.STAY, 0.96),
)

_WORD_SCORES: tuple[tuple[str, Intent, float], ...] = (
    ("follow", Intent.FOLLOW, 0.90),
    ("stay", Intent.STAY, 0.96),
    ("stop", Intent.STAY, 0.94),
    ("halt", Intent.STAY, 0.93),
    ("freeze", Intent.STAY, 0.90),
    ("fetch", Intent.FETCH, 0.90),
    ("approach", Intent.COME, 0.90),
)

_FETCH_OBJECT = re.compile(
    r"\b(?:fetch|get|grab|pick up|retrieve|collect|bring)\b(?:\s+\w+){0,5}\s+\b(?:hammer|tool|rock pick)\b"
)
_GIVE_CHAT = re.compile(r"\bgive me a (?:second|minute|moment|sec|break)\b")
_LEADING_FILLER = re.compile(
    r"^(?:hey rover|okay rover|ok rover|could you|would you|can you|please|hey|rover)\s+"
)
_BARE_COME = re.compile(r"(?:please )?(?:come|approach|here)(?: please)?")
_BARE_WAIT = re.compile(r"(?:please )?wait(?: please)?")
_BARE_GIVE = re.compile(r"(?:please )?(?:give|drop|release)(?: please)?")
_BARE_DOG = {
    "heel": (Intent.FOLLOW, 0.97),
    "sit": (Intent.STAY, 0.96),
    "settle": (Intent.STAY, 0.94),
}
# "hear" is the usual miss for "here" inside a longer phrase ("over hear").
# Applied to every token. "I hear you" does not become a Come command.
_TOKEN_HOMOPHONES = {
    "hear": "here",
}
# Only the whole utterance. A longer sentence keeps its own words, so
# "set it down" stays Give and "what the hell" stays chat.
_BARE_HOMOPHONES = {
    "heal": "heel",
    "healed": "heel",
    "heele": "heel",
    "hell": "heel",
    "weight": "wait",
    "waite": "wait",
}


def normalize(text: str, collapse_bare: bool = True) -> str:
    """Lowercase, strip punctuation, and remove polite lead-in words."""
    cleaned = text.lower().replace("'", "")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _LEADING_FILLER.sub("", cleaned).strip()
        cleaned = re.sub(r"\s+please$", "", cleaned).strip()
    cleaned = " ".join(_TOKEN_HOMOPHONES.get(token, token) for token in cleaned.split())
    if not collapse_bare:
        return cleaned
    return _BARE_HOMOPHONES.get(cleaned, cleaned)


def _without_phrases(text: str) -> str:
    reduced = text
    phrases = sorted((phrase for phrase, _, _ in _PHRASES), key=len, reverse=True)
    for phrase in phrases:
        reduced = re.sub(rf"\b{re.escape(phrase)}\b", " ", reduced)
    return re.sub(r"\s+", " ", reduced).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _partial_ratio(text: str, phrase: str) -> float:
    """Best similarity between a phrase and a window of the utterance."""
    if phrase in text:
        return 1.0
    window = len(phrase) + 4
    if len(text) <= window:
        return SequenceMatcher(None, text, phrase).ratio()
    best = 0.0
    last = len(text) - len(phrase) + 1
    for start in range(0, last, 2):
        chunk = text[start : start + window]
        best = max(best, SequenceMatcher(None, chunk, phrase).ratio())
    return best


class CommandParser:
    """Map one utterance to a command, a clarification, or ordinary chat."""

    def __init__(
        self,
        command_threshold: float = COMMAND_THRESHOLD,
        chat_threshold: float = CHAT_THRESHOLD,
    ) -> None:
        self._command_threshold = command_threshold
        self._chat_threshold = chat_threshold

    def parse(self, text: str) -> ParseResult:
        normalized = normalize(text)
        if not normalized:
            return ParseResult("chat", None, 0.0, {}, "empty")

        scores = self._exact_scores(normalized)
        if max(scores.values()) < self._command_threshold:
            scores = self._apply_fuzzy(normalized, scores)

        if _GIVE_CHAT.search(normalized):
            scores[Intent.GIVE] = 0.0

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_intent, top_score = ranked[0]
        second_score = ranked[1][1]
        slots = self._slots(top_intent, normalized)

        if top_score < self._chat_threshold:
            return ParseResult("chat", None, top_score, {}, "no_command")

        close_second = second_score >= 0.80 and top_score - second_score < 0.08
        if top_score < self._command_threshold or close_second:
            return ParseResult(
                "clarify",
                top_intent,
                top_score,
                slots,
                "low_confidence" if not close_second else "ambiguous",
            )

        return ParseResult("command", top_intent, top_score, slots, "matched")

    def _exact_scores(self, text: str) -> dict[Intent, float]:
        scores = {intent: 0.0 for intent in Intent}
        for phrase, intent, score in _PHRASES:
            if _contains_phrase(text, phrase):
                scores[intent] = max(scores[intent], score)
        for word, intent, score in _WORD_SCORES:
            if not re.search(rf"\b{word}\b", text):
                continue
            # Extra words that are not themselves a command block a lone
            # keyword. "follow the instructions" stays chat. "follow come here"
            # still sees both commands.
            outside = [token for token in _without_phrases(text).split() if token != word]
            if outside:
                continue
            scores[intent] = max(scores[intent], score)
        if _FETCH_OBJECT.search(text):
            scores[Intent.FETCH] = max(scores[Intent.FETCH], 0.96)
        if _BARE_COME.fullmatch(text):
            scores[Intent.COME] = max(scores[Intent.COME], 0.90)
        if _BARE_WAIT.fullmatch(text):
            scores[Intent.STAY] = max(scores[Intent.STAY], 0.90)
        if _BARE_GIVE.fullmatch(text):
            scores[Intent.GIVE] = max(scores[Intent.GIVE], 0.95)
        if text in _BARE_DOG:
            intent, score = _BARE_DOG[text]
            scores[intent] = max(scores[intent], score)
        if re.search(r"\b(?:do not follow|dont follow|stop following)\b", text):
            scores[Intent.FOLLOW] = 0.0
        return scores

    def _apply_fuzzy(
        self, text: str, scores: dict[Intent, float]
    ) -> dict[Intent, float]:
        updated = dict(scores)
        for phrase, intent, score in _PHRASES:
            if len(phrase) < 8 or updated[intent] >= self._command_threshold:
                continue
            ratio = _partial_ratio(text, phrase)
            if ratio >= 0.88:
                updated[intent] = max(updated[intent], score * ratio)
        return updated

    def _slots(self, intent: Intent, text: str) -> dict[str, str]:
        if intent is Intent.FETCH and (
            _FETCH_OBJECT.search(text) or re.search(r"\bfetch\b", text)
        ):
            return {"object": "rock_pick_hammer"}
        return {}
