"""Self-test: transcribe synthesized speech and check every command."""

import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from rover_voice.config import ON_MAC
from rover_voice.events import console_bus
from rover_voice.nlu.parser import Intent
from rover_voice.runtime import load_asr
from rover_voice.session import RoverSession

_SELF_TEST_CASES = (
    ("follow me", Intent.FOLLOW),
    ("wait here", Intent.STAY),
    ("fetch the hammer", Intent.FETCH),
    ("come here", Intent.COME),
    ("put it down", Intent.GIVE),
    ("walk alongside me", Intent.FOLLOW),
    ("do not move", Intent.STAY),
    ("go grab the rock hammer", Intent.FETCH),
    ("head over to me", Intent.COME),
    ("set the hammer down", Intent.GIVE),
)


def run_self_test(speak: bool, use_llm: bool) -> int:
    """Recognize synthesized commands, including paraphrases."""
    from rover_voice.nlu.understanding import CommandUnderstanding

    asr = load_asr(console_bus())
    if asr is None:
        return 1
    understanding = CommandUnderstanding()

    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for phrase, expected in _SELF_TEST_CASES:
            audio = _synthesize(phrase, root)
            started = time.perf_counter()
            heard = asr.transcribe(audio)
            elapsed_ms = (time.perf_counter() - started) * 1000
            parsed = understanding.interpret(heard)
            ok = parsed.intent is expected and parsed.kind == "command"
            status = "PASS" if ok else "FAIL"
            if not ok:
                failures += 1
            how = parsed.reason if parsed.reason else parsed.kind
            print(
                f"{status}: said {phrase!r} -> heard {heard!r} "
                f"-> {parsed.kind} {parsed.intent.name if parsed.intent else '-'} "
                f"via {how} ({elapsed_ms:.0f} ms)"
            )
        for phrase in ("what time is it", "hello there"):
            audio = _synthesize(phrase, root)
            heard = asr.transcribe(audio)
            parsed = understanding.interpret(heard)
            ok = parsed.kind == "chat"
            status = "PASS" if ok else "FAIL"
            if not ok:
                failures += 1
            print(
                f"{status}: said {phrase!r} -> heard {heard!r} -> {parsed.kind} "
                f"{parsed.intent.name if parsed.intent else '-'}"
            )

    session = RoverSession(speak=speak, use_llm=use_llm, log_dir=None)
    session.handle_text("follow me")
    # The chat model loads on the first sentence that is not a command.
    session.handle_text("what can you do?")
    if use_llm and session.chat is None:
        print("FAIL: chat model did not load")
        failures += 1
    if failures:
        print(f"Self-test failed ({failures} case(s)).")
        return 1
    print("Self-test passed.")
    return 0


def _synthesize(phrase: str, directory: Path) -> np.ndarray:
    spoken = directory / ("utt.aiff" if ON_MAC else "raw.wav")
    wav = directory / "utt.wav"
    if ON_MAC:
        subprocess.run(["say", "-o", str(spoken), phrase], check=True)
    else:
        subprocess.run(["espeak-ng", "-w", str(spoken), phrase], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(spoken),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
    )
    with wave.open(str(wav), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
