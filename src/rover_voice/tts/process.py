"""Spoken replies through a command-line voice: `say` on a Mac, espeak-ng on Linux."""

import logging
import re
import subprocess
import time

logger = logging.getLogger(__name__)


class ProcessSpeaker:
    """Speak through a command-line voice without blocking the microphone loop.

    A later command can stop the current sentence. The live loop keeps
    reading audio while the process is running.
    """

    program = ""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._proc: subprocess.Popen | None = None
        self._finished_at = 0.0

    def command(self, text: str) -> list[str]:
        raise NotImplementedError

    def speak(self, text: str) -> None:
        self.interrupt()
        if not self.enabled:
            return
        cleaned = re.sub(r"[\x00-\x1f]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return
        try:
            self._proc = subprocess.Popen(
                self.command(cleaned[:240]),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            # Replies are still reported as events; only the voice is lost.
            logger.warning("%s is not available. Replies will not be spoken.", self.program)
            self.enabled = False

    def interrupt(self) -> None:
        """Stop the sentence that is playing."""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._proc = None
            return
        proc.terminate()
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=0.2)
        self._finished_at = time.perf_counter()
        self._proc = None

    def wait(self) -> None:
        """Block until the current sentence ends. Used by the scripted test."""
        if self._proc is None:
            return
        self._proc.wait()
        self._finished_at = time.perf_counter()
        self._proc = None

    def poll(self) -> None:
        if self._proc is not None and self._proc.poll() is not None:
            self._finished_at = time.perf_counter()
            self._proc = None

    @property
    def busy(self) -> bool:
        self.poll()
        return self._proc is not None

    def echoing(self, grace_s: float = 0.12) -> bool:
        """True while our own reply can still be in the microphone."""
        if not self.enabled:
            return False
        if self.busy:
            return True
        return (time.perf_counter() - self._finished_at) < grace_s


class MacSpeaker(ProcessSpeaker):
    program = "say"

    def command(self, text: str) -> list[str]:
        return ["say", "-r", "210", text]


class EspeakSpeaker(ProcessSpeaker):
    """espeak-ng, installed with `apt install espeak-ng`."""

    program = "espeak-ng"

    def command(self, text: str) -> list[str]:
        return ["espeak-ng", "-s", "170", text]
