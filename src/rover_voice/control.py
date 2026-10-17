"""Requests from outside the voice loop, such as a ROS node.

Other threads queue requests here. The voice loop applies them between
microphone frames, so the session, speaker, and decoder stay on one thread.
"""

import queue
import threading
from dataclasses import dataclass

from rover_voice.events import Reply, Status
from rover_voice.session import RoverSession


@dataclass(frozen=True)
class Say:
    """Speak for the rover. The live loop treats it as the rover's own voice."""

    text: str


@dataclass(frozen=True)
class TextInput:
    """An utterance that was typed or recognized elsewhere."""

    text: str


@dataclass(frozen=True)
class SetListening:
    enabled: bool


Request = Say | TextInput | SetListening


class LoopControl:
    """Thread-safe requests in, applied by the voice loop's thread."""

    def __init__(self) -> None:
        self.listening = True
        self._requests: queue.Queue[Request] = queue.Queue()
        self._stop = threading.Event()

    def submit(self, request: Request) -> None:
        self._requests.put(request)

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def wait(self, timeout: float) -> None:
        """Sleep until a request arrives, stop() is called, or timeout."""
        if self._requests.empty():
            self._stop.wait(timeout)

    def apply(self, session: RoverSession) -> bool:
        """Apply queued requests. Return False when the session should end."""
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return True
            match request:
                case Say(text):
                    session.events.emit(Reply(text))
                    session.speaker.speak(text)
                case TextInput(text):
                    if not session.handle_text(text):
                        return False
                case SetListening(enabled):
                    if enabled != self.listening:
                        self.listening = enabled
                        message = "Listening." if enabled else "Listening paused."
                        session.events.emit(Status(message))
