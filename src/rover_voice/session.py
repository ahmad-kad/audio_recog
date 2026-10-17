"""Shared session used by the microphone loop and the typed loop."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rover_voice.config import CHAT_FALLBACK, CLARIFY_SPEECH, LLM_MODEL, QUIT_PHRASES
from rover_voice.events import (
    Clarify,
    CommandAccepted,
    CommandRejected,
    EventBus,
    Heard,
    Reply,
    SessionEnded,
    StateChanged,
    Status,
    console_bus,
)
from rover_voice.nlu.parser import normalize
from rover_voice.nlu.understanding import CommandUnderstanding
from rover_voice.rover.arbiter import CommandArbiter, Decision, RoverState
from rover_voice.tts.base import Speaker

logger = logging.getLogger("rover_voice")


class RoverSession:
    """Parse speech, report the action as events, and speak the reply."""

    def __init__(
        self,
        speak: bool = True,
        use_llm: bool = True,
        log_dir: Path | None = Path("logs"),
        events: EventBus | None = None,
        speaker: Speaker | None = None,
        allow_quit: bool = True,
    ) -> None:
        self.session_id = (
            f"rover_mac_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        )
        self.state = RoverState()
        self.events = events or console_bus()
        self.understanding = CommandUnderstanding(
            on_status=lambda message: self.events.emit(Status(message))
        )
        self.parser = self.understanding.parser
        self.arbiter = CommandArbiter()
        if speaker is None:
            from rover_voice.tts import create_speaker

            speaker = create_speaker(enabled=speak)
        self.speaker = speaker
        # A robot service keeps listening; "goodbye" is then ordinary speech.
        self.allow_quit = allow_quit
        self.history: list[dict[str, str]] = []
        self.last_intent: str | None = None
        self.chat = None
        self._use_llm = use_llm
        self._log_path: Path | None = None
        self._open_log(log_dir)

    def handle_text(
        self,
        text: str,
        asr_ms: float | None = None,
        direction: str | None = None,
        direction_deg: float | None = None,
        started_at: float | None = None,
    ) -> bool:
        """Handle one utterance. Return False when the session should end.

        direction_deg is the rover angle, clockwise from the front, and
        started_at the wall-clock time speech began; both pass through to
        the events.
        """
        cleaned = " ".join(text.split())
        normalized = normalize(cleaned)
        if not normalized:
            return True

        self.events.emit(Heard(cleaned, asr_ms, direction, direction_deg, started_at))

        if self.allow_quit and normalized in QUIT_PHRASES:
            self.last_intent = "QUIT"
            self._say("Signing off.")
            self._record(cleaned, "quit", None, 1.0, False, None, "Signing off.")
            self.events.emit(SessionEnded())
            return False

        parsed = self.understanding.interpret(cleaned)
        decision = self.arbiter.decide(parsed, self.state)
        if decision.status == "approved" and decision.intent is not None:
            self.state.apply(decision.intent)
            self.events.emit(
                CommandAccepted(
                    decision.intent.name,
                    decision.confidence,
                    by_meaning=decision.reason == "meaning",
                    slots=dict(decision.slots),
                    direction=direction,
                    direction_deg=direction_deg,
                    started_at=started_at,
                    text=cleaned,
                )
            )
            self._say(decision.speech)
            self.events.emit(StateChanged(self.state.command))
        elif decision.status == "rejected":
            name = decision.intent.name if decision.intent else "UNKNOWN"
            self.events.emit(CommandRejected(name, decision.reason))
            self._say(decision.speech)
            self.events.emit(StateChanged(self.state.command))
        elif decision.status == "clarify":
            self.events.emit(Clarify(decision.confidence))
            self._say(decision.speech)
        else:
            speech, llm_ms = self._chat(cleaned)
            # A short command-shaped reply would sound like the rover already
            # moved. Longer answers can mention the command words safely.
            if len(speech.split()) <= 6 and self.parser.parse(speech).kind == "command":
                speech = CHAT_FALLBACK
            self.events.emit(Reply(speech, llm_ms))
            self.speaker.speak(speech)
            decision = Decision("chat", None, parsed.confidence, None, speech, "chat", {})
            self._remember(cleaned, speech)

        self.last_intent = decision.intent.name if decision.intent else decision.status.upper()
        self._record(
            cleaned,
            decision.status,
            decision.intent.name if decision.intent else None,
            decision.confidence,
            decision.status == "approved",
            decision.action,
            decision.speech,
            asr_ms=asr_ms,
        )
        return True

    def did_not_understand(self) -> None:
        self.events.emit(Clarify())
        self._say(CLARIFY_SPEECH)
        self._record("", "clarify", None, 0.0, False, None, CLARIFY_SPEECH)

    def _chat(self, text: str) -> tuple[str, float | None]:
        if not self._use_llm:
            return CHAT_FALLBACK, None
        if self.chat is None:
            self.chat = self._load_chat()
        if self.chat is None:
            return CHAT_FALLBACK, None
        try:
            speech = self.chat.reply(text, self.state.describe(), self.history)
            return speech, self.chat.last_ms
        except Exception as exc:  # any model failure falls back to a fixed reply
            logger.exception("Chat model failed")
            self.events.emit(Status(f"Chat model failed: {exc}"))
            return CHAT_FALLBACK, None

    def _say(self, speech: str) -> None:
        self.events.emit(Reply(speech))
        self.speaker.speak(speech)

    def _remember(self, user_text: str, speech: str) -> None:
        if not user_text or not speech:
            return
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": speech})
        self.history = self.history[-6:]

    def _load_chat(self):
        from rover_voice.nlu.llm_chat import create_chat

        self.events.emit(Status(f"Loading chat model {LLM_MODEL}..."))
        try:
            chat = create_chat()
        except Exception as exc:  # missing weights, no memory, bad install
            self.events.emit(
                Status(
                    "Chat model unavailable "
                    f"({exc}). Commands still work. Chat will use a short fixed reply."
                )
            )
            logger.exception("Chat model unavailable")
            return None
        self.events.emit(Status(f"Chat model ready ({chat.model_id})."))
        return chat

    def _open_log(self, log_dir: Path | None) -> None:
        if log_dir is None:
            return
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"{self.session_id}.jsonl"
        self._write({"type": "session", "session_id": self.session_id})

    def _record(
        self,
        text: str,
        status: str,
        intent: str | None,
        confidence: float,
        approved: bool,
        action: str | None,
        response: str,
        asr_ms: float | None = None,
    ) -> None:
        self._write(
            {
                "type": "utterance",
                "session_id": self.session_id,
                "t": datetime.now(timezone.utc).isoformat(),
                "text": text,
                "speaker": "unknown",
                "status": status,
                "intent": intent,
                "confidence": round(confidence, 3),
                "approved": approved,
                "action": action,
                "response": response,
                "asr_ms": None if asr_ms is None else round(asr_ms, 1),
                "state": self.state.describe(),
            }
        )

    def _write(self, record: dict) -> None:
        if self._log_path is None:
            return
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
