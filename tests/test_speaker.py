"""Speaker control that must not block the live loop."""

from rover_voice.tts.process import MacSpeaker


def test_disabled_speaker_does_not_block_or_look_like_echo():
    speaker = MacSpeaker(enabled=False)
    speaker.speak("Okay, follow.")
    speaker.interrupt()
    speaker.wait()
    speaker.poll()
    assert speaker.busy is False
    assert speaker.echoing() is False
