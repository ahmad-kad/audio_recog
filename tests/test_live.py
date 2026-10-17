"""The live loop fires a stable command before the utterance ends."""

import numpy as np

from rover_voice.audio.vad import UtteranceSegmenter
from rover_voice.live import LiveDecoder
from rover_voice.session import RoverSession


class _Script:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def transcribe(self, audio: np.ndarray) -> str:
        del audio
        self.calls += 1
        return self.text


def _tone() -> np.ndarray:
    count = 480
    time_axis = np.arange(count, dtype=np.float32) / 16000
    return (0.1 * np.sin(2 * np.pi * 200 * time_axis)).astype(np.float32)


def _decoder(text: str) -> tuple[LiveDecoder, RoverSession, _Script]:
    session = RoverSession(speak=False, use_llm=False, log_dir=None)
    asr = _Script(text)
    segmenter = UtteranceSegmenter(sample_rate=16000)
    silence = np.zeros(480, dtype=np.float32)
    decoder = LiveDecoder(session, asr, segmenter)
    for _ in range(20):
        assert decoder.feed(silence)
    return decoder, session, asr


def test_heel_is_accepted_while_speech_is_still_open():
    decoder, session, asr = _decoder("heel")
    accepted = False
    for _ in range(20):
        assert decoder.feed(_tone())
        if session.last_intent == "FOLLOW":
            accepted = True
            break
    assert accepted
    assert asr.calls >= 1
    assert decoder.segmenter.in_speech


class _Array:
    """Stand-in for the reSpeaker direction tracker."""

    def __init__(self, speech: bool, from_speaker: bool = False) -> None:
        self.speech = speech
        self.from_speaker = from_speaker

    def speech_seen_since(self, start: float) -> bool:
        del start
        return self.speech

    def from_speaker_since(self, start: float) -> bool:
        del start
        return self.from_speaker

    def describe_since(self, start: float) -> str:
        del start
        return "→ right (90°)"

    def degrees_since(self, start: float) -> float:
        del start
        return 90.0


def _array_decoder(text: str, array: _Array) -> tuple[LiveDecoder, RoverSession, _Script]:
    decoder, session, asr = _decoder(text)
    decoder.directions = array
    return decoder, session, asr


def _speak_then_pause(decoder: LiveDecoder) -> None:
    silence = np.zeros(480, dtype=np.float32)
    for _ in range(12):
        assert decoder.feed(_tone())
    for _ in range(12):
        assert decoder.feed(silence)


def test_noise_without_array_speech_is_not_transcribed():
    decoder, session, asr = _array_decoder("heel", _Array(speech=False))
    _speak_then_pause(decoder)
    assert asr.calls == 0
    assert session.last_intent is None


def test_command_with_array_speech_fires_and_names_the_side(capsys):
    decoder, session, _ = _array_decoder("heel", _Array(speech=True))
    _speak_then_pause(decoder)
    assert session.last_intent == "FOLLOW"
    assert "FROM: → right (90°)" in capsys.readouterr().out


def test_speech_from_the_rover_speaker_is_ignored_while_it_talks():
    decoder, session, _ = _array_decoder("stay", _Array(speech=True, from_speaker=True))
    session.speaker.echoing = lambda *args, **kwargs: True
    _speak_then_pause(decoder)
    assert session.last_intent is None
