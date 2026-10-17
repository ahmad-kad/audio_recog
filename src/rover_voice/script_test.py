"""Guided test: say each line in scripts/test_lines.txt and score the command."""

import time
from pathlib import Path

import numpy as np

from rover_voice.asr.base import ASRBackend
from rover_voice.audio.base import Microphone
from rover_voice.audio.vad import UtteranceSegmenter
from rover_voice.runtime import calibrate_noise, load_asr, open_input
from rover_voice.session import RoverSession


def run_script(
    speak: bool,
    use_llm: bool,
    text_mode: bool,
    debug: bool,
    input_device: str | None,
) -> int:
    """Prompt each line in scripts/test_lines.txt and score the command."""
    cases = _load_script(Path("scripts/test_lines.txt"))
    session = RoverSession(speak=speak, use_llm=use_llm)
    if text_mode:
        return _score_script_text(session, cases)
    return _score_script_live(session, cases, debug=debug, input_device=input_device)


def _score_script_text(session: RoverSession, cases: list[tuple[str, str]]) -> int:
    print("Text run of the test script. Each line is recognized and spoken.")
    passed = 0
    for index, (expected, phrase) in enumerate(cases, start=1):
        print(f"\n[{index}/{len(cases)}] {phrase}")
        session.handle_text(phrase)
        session.speaker.wait()
        if _score_line(session.last_intent, expected):
            passed += 1
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


def _score_script_live(
    session: RoverSession,
    cases: list[tuple[str, str]],
    debug: bool,
    input_device: str | None,
) -> int:
    asr = load_asr(session.events)
    if asr is None:
        return 1
    microphone = open_input(input_device, session.events)
    if microphone is None:
        return 1
    segmenter = calibrate_noise(microphone, session.events)

    print("Say each line when asked. Wait for the spoken reply before the next one.")
    passed = 0
    try:
        for index, (expected, phrase) in enumerate(cases, start=1):
            print(f"\n[{index}/{len(cases)}] Say: {phrase}")
            print(f"Expect: {expected}")
            heard = _listen_once(microphone, segmenter, asr, session, debug=debug)
            if not heard:
                print("FAIL  no speech heard")
                continue
            if session.last_intent == "QUIT":
                break
            if _score_line(session.last_intent, expected):
                passed += 1
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        microphone.close()
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


def _listen_once(
    microphone: Microphone,
    segmenter: UtteranceSegmenter,
    asr: ASRBackend,
    session: RoverSession,
    debug: bool,
) -> bool:
    """Capture one utterance. Return False on timeout."""
    deadline = time.perf_counter() + 12.0
    segmenter.reset()
    microphone.drain()
    while time.perf_counter() < deadline:
        frame = microphone.read(timeout=0.5)
        if frame is None:
            continue
        result = segmenter.feed(frame)
        if result.event == "speech_start":
            if debug:
                print(
                    "Speech detected. "
                    f"(level {segmenter.last_rms:.3f}, threshold {segmenter.threshold:.3f})"
                )
            else:
                print("Speech detected.")
            continue
        if result.event != "utterance" or result.audio is None:
            continue
        _handle_utterance(session, asr, result.audio)
        session.speaker.wait()
        _drop_echo_tail(microphone)
        segmenter.reset()
        return True
    return False


def _score_line(got: str | None, expected: str) -> bool:
    actual = got or "NONE"
    if actual == expected:
        print(f"PASS  {actual}")
        return True
    print(f"FAIL  heard {actual}, expected {expected}")
    return False


def _load_script(path: Path) -> list[tuple[str, str]]:
    cases = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        expected, phrase = line.split("|", 1)
        cases.append((expected.strip(), phrase.strip()))
    if not cases:
        raise SystemExit(f"No test lines in {path}")
    return cases


def _drop_echo_tail(microphone: Microphone, seconds: float = 0.06) -> None:
    """Drop the rover's own voice, then keep listening for the next command.

    Audio queued during the spoken reply is discarded. Only a short tail
    after the reply ends is dropped, so a command that starts as the reply
    finishes is not thrown away.
    """
    microphone.drain()
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        microphone.read(timeout=0.02)


def _handle_utterance(session: RoverSession, asr: ASRBackend, audio: np.ndarray) -> bool:
    started = time.perf_counter()
    try:
        text = asr.transcribe(audio)
    except Exception as exc:  # a failed clip counts as not understood
        print(f"Recognition failed: {exc}")
        session.did_not_understand()
        return True
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not text:
        session.did_not_understand()
        return True
    return session.handle_text(text, asr_ms=elapsed_ms)
