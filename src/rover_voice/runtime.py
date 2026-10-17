"""Shared startup for the listening modes, and the live listening loop."""

import time
from typing import Callable

from rover_voice.asr.base import ASRBackend
from rover_voice.audio.base import Microphone
from rover_voice.audio.vad import UtteranceSegmenter
from rover_voice.config import ASR_BACKEND
from rover_voice.control import LoopControl
from rover_voice.errors import AudioDeviceError, ModelLoadError
from rover_voice.events import EventBus, Status
from rover_voice.session import RoverSession


def load_asr(
    events: EventBus, backend: str = ASR_BACKEND, model_id: str = ""
) -> ASRBackend | None:
    """Load and warm up the speech model. None if it cannot load."""
    from rover_voice.asr import create_asr

    try:
        asr = create_asr(backend, model_id)
        events.emit(Status(f"Loading speech model {asr.model_id}..."))
        asr.warmup()
    except ModelLoadError as exc:
        events.emit(Status(str(exc)))
        return None
    events.emit(Status(f"Speech model ready ({asr.model_id})."))
    return asr


def open_input(device: str | None, events: EventBus) -> Microphone | None:
    """Open the Mac microphone or the reSpeaker bridge. None on failure."""
    from rover_voice.audio.capture import open_microphone

    try:
        microphone = open_microphone(device)
        name = microphone.start(device)
    except AudioDeviceError as exc:
        events.emit(Status(str(exc)))
        return None
    events.emit(Status(f"Microphone: {name}"))
    return microphone


def calibrate_noise(
    microphone: Microphone, events: EventBus, seconds: float = 2.0
) -> UtteranceSegmenter:
    """Learn the room's noise floor before listening for speech."""
    segmenter = UtteranceSegmenter()
    events.emit(Status("Calibrating microphone..."))
    deadline = time.perf_counter() + seconds
    while not segmenter.calibrated and time.perf_counter() < deadline:
        frame = microphone.read(timeout=0.5)
        if frame is not None:
            segmenter.feed(frame)
    return segmenter


def run_live(
    session: RoverSession,
    debug: bool = False,
    input_device: str | None = None,
    control: LoopControl | None = None,
    asr: ASRBackend | None = None,
    on_open: Callable[[Microphone], None] | None = None,
) -> int:
    """Listen until Ctrl-C, a quit phrase, or control.stop().

    A caller that runs the loop as a service passes control to send
    requests in, asr to choose the speech model, and on_open to reach the
    microphone (for its direction stream).
    """
    from rover_voice.live import LiveDecoder

    events = session.events
    control = control or LoopControl()
    asr = asr or load_asr(events)
    if asr is None:
        return 1
    microphone = open_input(input_device, events)
    if microphone is None:
        return 1
    if on_open is not None:
        on_open(microphone)
    segmenter = calibrate_noise(microphone, events)
    events.emit(Status("Listening. Say a command, or just talk. Ctrl-C to quit."))
    events.emit(
        Status(
            "A clear command answers while you are still speaking. "
            "A new command interrupts the reply."
        )
    )

    decoder = LiveDecoder(
        session, asr, segmenter, debug=debug, directions=microphone.directions
    )
    try:
        while not control.stopped:
            if not control.apply(session):
                break
            frame = microphone.read(timeout=0.5)
            if frame is None or not control.listening:
                continue
            if not decoder.feed(frame):
                break
    except KeyboardInterrupt:
        events.emit(Status("Stopped."))
    finally:
        session.speaker.interrupt()
        microphone.close()
    return 0


def run_headless(session: RoverSession, control: LoopControl) -> int:
    """No microphone: handle text and say requests until control.stop()."""
    try:
        while not control.stopped:
            if not control.apply(session):
                break
            session.speaker.poll()
            control.wait(0.05)
    except KeyboardInterrupt:
        session.events.emit(Status("Stopped."))
    finally:
        session.speaker.interrupt()
    return 0
