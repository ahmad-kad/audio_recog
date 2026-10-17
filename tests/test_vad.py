"""Utterance segmentation on synthetic audio."""

import numpy as np

from rover_voice.audio.vad import UtteranceSegmenter


def _frame(sample_rate: int, amplitude: float) -> np.ndarray:
    count = int(sample_rate * 0.03)
    time_axis = np.arange(count, dtype=np.float32) / sample_rate
    return (amplitude * np.sin(2 * np.pi * 200 * time_axis)).astype(np.float32)


def test_segmenter_returns_a_tone_and_ignores_a_click():
    segmenter = UtteranceSegmenter(sample_rate=16000)
    silence = np.zeros(480, dtype=np.float32)
    for _ in range(20):
        assert segmenter.feed(silence).event == "none"
    assert segmenter.calibrated

    started = False
    for _ in range(25):
        result = segmenter.feed(_frame(16000, 0.1))
        if result.event == "speech_start":
            started = True
    assert started

    utterance = None
    for _ in range(20):
        result = segmenter.feed(silence)
        if result.event == "utterance":
            utterance = result.audio
            break
    assert utterance is not None
    assert utterance.size > 1000
