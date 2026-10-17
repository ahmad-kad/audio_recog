"""Backend choice for a Mac or a Linux rover computer. No models load."""

import pytest

from rover_voice.asr import create_asr
from rover_voice.errors import ModelLoadError
from rover_voice.nlu.llm_chat import create_chat
from rover_voice.tts import create_speaker
from rover_voice.tts.process import EspeakSpeaker, MacSpeaker


def test_asr_backends_are_chosen_by_name():
    assert type(create_asr("faster-whisper")).__name__ == "FasterWhisperASR"
    assert create_asr("faster-whisper").model_id == "base.en"
    assert type(create_asr("mlx")).__name__ == "MlxWhisperASR"
    assert create_asr("faster-whisper", "small.en").model_id == "small.en"
    with pytest.raises(ModelLoadError):
        create_asr("vosk")


def test_unknown_chat_backend_fails_clearly():
    with pytest.raises(ModelLoadError):
        create_chat("llama")


def test_speakers():
    assert isinstance(create_speaker(backend="espeak-ng"), EspeakSpeaker)
    assert isinstance(create_speaker(backend="say"), MacSpeaker)
    assert create_speaker(backend="none").enabled is False
    assert EspeakSpeaker().command("hi")[0] == "espeak-ng"


def test_missing_voice_program_disables_speech():
    speaker = EspeakSpeaker()
    speaker.program = "espeak-ng"
    speaker.command = lambda text: ["/nonexistent/voice-program", text]  # type: ignore[method-assign]
    speaker.speak("hello")
    assert speaker.enabled is False
    assert speaker.busy is False
