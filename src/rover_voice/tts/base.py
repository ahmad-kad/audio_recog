"""Speaker interface. The Mac uses `say`; a rover can plug in its own."""

from typing import Protocol


class Speaker(Protocol):
    enabled: bool

    def speak(self, text: str) -> None:
        """Start speaking without blocking. Cuts off any sentence in progress."""

    def interrupt(self) -> None: ...

    def wait(self) -> None:
        """Block until the current sentence ends."""

    def poll(self) -> None: ...

    @property
    def busy(self) -> bool: ...

    def echoing(self, grace_s: float = 0.12) -> bool:
        """True while the rover's own voice can still be in the microphone."""
