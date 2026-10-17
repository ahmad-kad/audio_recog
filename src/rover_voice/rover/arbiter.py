"""Turn a parsed utterance into a command name.

Hearing Follow, Stay, Fetch, Come, or Give only reports that command.
Following distance, holding position, grasping the hammer, driving to the
astronaut, and placing the hammer are left to the rover later.
"""

from dataclasses import dataclass

from rover_voice.config import CLARIFY_SPEECH
from rover_voice.nlu.parser import Intent, ParseResult


@dataclass
class RoverState:
    """The last voice command. This does not move the rover."""

    command: str = "none"

    def apply(self, intent: Intent) -> None:
        self.command = intent.value

    def describe(self) -> str:
        return f"last voice command {self.command}"


@dataclass(frozen=True)
class Decision:
    status: str
    intent: Intent | None
    confidence: float
    action: str | None
    speech: str
    reason: str
    slots: dict[str, str]


_SPEECH = {
    Intent.FOLLOW: "Okay, follow.",
    Intent.STAY: "Okay, stay.",
    Intent.FETCH: "Okay, fetch.",
    Intent.COME: "Okay, come.",
    Intent.GIVE: "Okay, give.",
}


class CommandArbiter:
    """Accept a recognized command and leave the rover behavior unimplemented."""

    def decide(self, parsed: ParseResult, state: RoverState) -> Decision:
        del state
        if parsed.kind == "chat":
            return Decision("chat", None, parsed.confidence, None, "", "chat", {})
        if parsed.kind == "clarify" or parsed.intent is None:
            return Decision(
                "clarify",
                parsed.intent,
                parsed.confidence,
                None,
                CLARIFY_SPEECH,
                parsed.reason,
                parsed.slots,
            )

        intent = parsed.intent
        reason = "meaning" if parsed.reason == "meaning" else "accepted"
        return Decision(
            "approved",
            intent,
            parsed.confidence,
            intent.value,
            _SPEECH[intent],
            reason,
            parsed.slots,
        )
