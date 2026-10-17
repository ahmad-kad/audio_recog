"""Phrase match first, then meaning match for other wording."""

from typing import Callable

from rover_voice.nlu.meaning import MeaningMatcher
from rover_voice.nlu.parser import CommandParser, ParseResult


class CommandUnderstanding:
    """Resolve one utterance to a command without running rover behavior."""

    def __init__(self, on_status: Callable[[str], None] = print) -> None:
        self.parser = CommandParser()
        self._meaning: MeaningMatcher | None = None
        self._on_status = on_status

    def interpret(self, text: str) -> ParseResult:
        parsed = self.parser.parse(text)
        if parsed.kind != "chat":
            return parsed
        meant = self.meaning.match(text)
        if meant is None:
            return parsed
        return meant

    @property
    def meaning(self) -> MeaningMatcher:
        # Known phrases never reach this. The embedding model loads on the
        # first sentence that is not already a command.
        if self._meaning is None:
            self._on_status("Loading meaning model...")
            self._meaning = MeaningMatcher()
            self._on_status("Meaning model ready.")
        return self._meaning
