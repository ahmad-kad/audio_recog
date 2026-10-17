"""Speaker output."""

from rover_voice.config import TTS_BACKEND
from rover_voice.tts.base import Speaker


def create_speaker(enabled: bool = True, backend: str = TTS_BACKEND) -> Speaker:
    """`say` on a Mac, espeak-ng on Linux. ROVER_TTS=none keeps the rover quiet."""
    from rover_voice.tts.process import EspeakSpeaker, MacSpeaker

    if backend == "none":
        return MacSpeaker(enabled=False)
    if backend == "espeak-ng":
        return EspeakSpeaker(enabled=enabled)
    return MacSpeaker(enabled=enabled)
