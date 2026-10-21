"""Microphone faults reported for the terminal and for /diagnostics."""

import time

import numpy as np

from rover_voice.audio.health import AudioMonitor
from rover_voice.config import SAMPLE_RATE


def _tone(seconds: float, amplitude: float) -> np.ndarray:
    count = int(SAMPLE_RATE * seconds)
    axis = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 200 * axis)).astype(np.float32)


def test_clipping_and_silence_and_a_dead_stream():
    monitor = AudioMonitor()
    normal = _tone(0.03, 0.1)
    monitor.observe(normal)
    assert monitor.report().level == "ok"

    for _ in range(5):
        monitor.observe(np.ones(480, dtype=np.float32))
    clipped = monitor.report()
    assert clipped.level == "error"
    assert clipped.message == "Audio is clipping."
    assert clipped.peak == 1.0

    monitor.observe(normal)
    assert monitor.report().level == "ok"

    monitor.observe(np.zeros(SAMPLE_RATE * 3, dtype=np.float32))
    quiet = monitor.report()
    assert quiet.level == "warn"
    assert quiet.message == "Audio level is near silence."

    monitor.observe(normal)
    assert monitor.report().level == "ok"

    monitor.set_stalled(True)
    stalled = monitor.report()
    assert stalled.level == "error"
    assert stalled.message == "No audio from the reSpeaker."
    monitor.set_stalled(False)
    monitor.observe(normal)
    assert monitor.report().level == "ok"

    monitor._last_frame_at = time.monotonic() - 3
    missing = monitor.report()
    assert missing.level == "error"
    assert missing.message == "No audio frames."
