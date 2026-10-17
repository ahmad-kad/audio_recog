"""Continuous listen path.

Audio is transcribed while the person is still speaking. A command the
grammar already trusts fires immediately. The reply does not close the
microphone: a different command interrupts it. The meaning model and the
chat model run only after a finished utterance that was not a command.

With the reSpeaker Flex, a turn also needs speech energy from the array,
and speech from the rover's own speaker direction is ignored while it talks.
"""

import time

from rover_voice.asr.base import ASRBackend
from rover_voice.audio.direction import DirectionSource, wall_time
from rover_voice.audio.vad import UtteranceSegmenter
from rover_voice.config import (
    EARLY_HOLD_SILENCE_S,
    PARTIAL_INTERVAL_S,
    PARTIAL_MIN_SPEECH_S,
    QUIT_PHRASES,
)
from rover_voice.events import Ignored, Status
from rover_voice.nlu.parser import Intent, normalize
from rover_voice.nlu.spotter import spot_command
from rover_voice.session import RoverSession


class LiveDecoder:
    """Feed microphone frames and dispatch commands without taking turns."""

    def __init__(
        self,
        session: RoverSession,
        asr: ASRBackend,
        segmenter: UtteranceSegmenter,
        debug: bool = False,
        directions: DirectionSource | None = None,
    ) -> None:
        self.session = session
        self.asr = asr
        self.segmenter = segmenter
        self.debug = debug
        self.directions = directions
        self.events = session.events
        self._turn_started = 0.0
        self._opened_while_speaking = False
        self._closed = False
        self._committed_intent: Intent | None = None
        self._last_partial = 0.0
        self._hold_decoded = False

    def feed(self, frame) -> bool:
        """Consume one frame. Return False when the session should end."""
        self.session.speaker.poll()
        result = self.segmenter.feed(frame)
        if result.event == "speech_start":
            self._begin_turn()
            return True
        if result.event == "utterance" and result.audio is not None:
            return self._end_turn(result.audio)
        if self.segmenter.in_speech:
            return self._maybe_partial()
        return True

    def _begin_turn(self) -> None:
        self._opened_while_speaking = self.session.speaker.echoing()
        self._closed = False
        self._committed_intent = None
        self._last_partial = 0.0
        self._hold_decoded = False
        # Speech started a few frames before the gate opened.
        self._turn_started = time.monotonic() - 0.3
        if self.debug:
            self._status(
                "Speech detected. "
                f"(level {self.segmenter.last_rms:.3f}, "
                f"threshold {self.segmenter.threshold:.3f})"
            )
        else:
            self._status("Speech detected.")

    def _maybe_partial(self) -> bool:
        if self._closed or not self._array_heard_speech() or not self._partial_due():
            return True
        text, elapsed_ms = self._transcribe(self.segmenter.preview())
        if not text:
            return True
        if self.session.allow_quit and normalize(text) in QUIT_PHRASES:
            return self._dispatch(text, elapsed_ms)
        spotted = spot_command(
            self.session.parser,
            text,
            self.segmenter.trailing_silence_s,
        )
        if spotted is None or spotted.intent is None:
            return True
        if spotted.intent == self._committed_intent:
            return True
        if self._is_own_reply(text):
            return True
        return self._dispatch(text, elapsed_ms)

    def _partial_due(self) -> bool:
        if self.segmenter.speech_s < PARTIAL_MIN_SPEECH_S:
            return False
        silence = self.segmenter.trailing_silence_s
        if silence >= EARLY_HOLD_SILENCE_S and not self._hold_decoded:
            self._hold_decoded = True
            self._last_partial = time.perf_counter()
            return True
        if silence < EARLY_HOLD_SILENCE_S:
            self._hold_decoded = False
        now = time.perf_counter()
        if now - self._last_partial < PARTIAL_INTERVAL_S:
            return False
        self._last_partial = now
        return True

    def _end_turn(self, audio) -> bool:
        if self._closed:
            self._status("Listening.")
            return True
        if not self._array_heard_speech():
            self.events.emit(Ignored("the array heard noise, not speech."))
            self._status("Listening.")
            return True
        text, elapsed_ms = self._transcribe(audio)
        if not text:
            if not self._opened_while_speaking:
                self.session.did_not_understand()
            self._status("Listening.")
            return True
        if self._is_own_reply(text):
            self._status("Listening.")
            return True
        keep = self._dispatch(text, elapsed_ms)
        if keep:
            self._status("Listening.")
        return keep

    def _dispatch(self, text: str, elapsed_ms: float) -> bool:
        if self._opened_while_speaking:
            self.session.speaker.interrupt()
        heading = None
        degrees = None
        if self.directions is not None:
            heading = self.directions.describe_since(self._turn_started)
            degrees = self.directions.degrees_since(self._turn_started)
        keep = self.session.handle_text(
            text,
            asr_ms=elapsed_ms,
            direction=heading,
            direction_deg=degrees,
            started_at=wall_time(self._turn_started),
        )
        self._closed = True
        parsed = self.session.parser.parse(text)
        self._committed_intent = parsed.intent
        return keep

    def _is_own_reply(self, text: str) -> bool:
        """Ignore the speaker playing "Okay, follow" back into the microphone."""
        if not self._opened_while_speaking:
            return False
        if normalize(text) in QUIT_PHRASES:
            return False
        if self.directions is not None and self.directions.from_speaker_since(
            self._turn_started
        ):
            if self.debug:
                self.events.emit(Ignored("speech came from the rover's speaker."))
            return True
        parsed = self.session.parser.parse(text)
        if parsed.kind != "command" or parsed.intent is None:
            return True
        return parsed.intent.value == self.session.state.command

    def _status(self, message: str) -> None:
        self.events.emit(Status(message))

    def _array_heard_speech(self) -> bool:
        if self.directions is None:
            return True
        return self.directions.speech_seen_since(self._turn_started)

    def _transcribe(self, audio) -> tuple[str, float]:
        started = time.perf_counter()
        try:
            text = self.asr.transcribe(audio)
        except Exception as exc:  # a failed clip must not stop listening
            self._status(f"Recognition failed: {exc}")
            return "", 0.0
        elapsed_ms = (time.perf_counter() - started) * 1000
        return text, elapsed_ms
