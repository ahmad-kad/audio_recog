"""Voice loop events to ROS message fields, without importing ROS.

The node fills messages from these dictionaries, so the conversions are
unit-tested with plain pytest on any machine.
"""

import math

from rover_voice.audio.direction import Calibration, DirectionSample, sample_degrees
from rover_voice.events import CommandAccepted, Heard


def ros_yaw(rover_degrees: float) -> float:
    """Rover angle (clockwise from the front, 90 = right) to REP-103 radians.

    REP-103 measures counterclockwise from +x (ahead), so right is -pi/2.
    The result is in (-pi, pi].
    """
    yaw = -math.radians(rover_degrees)
    yaw = math.atan2(math.sin(yaw), math.cos(yaw))
    return math.pi if yaw <= -math.pi else yaw


def stamp(wall_time: float | None, now: float) -> tuple[int, int]:
    """Seconds and nanoseconds for a header. Falls back to now."""
    value = now if wall_time is None else wall_time
    sec = int(math.floor(value))
    nanosec = min(int(round((value - sec) * 1e9)), 999_999_999)
    return sec, nanosec


def _direction(degrees: float | None) -> dict:
    if degrees is None:
        return {"has_direction": False, "direction": 0.0}
    return {"has_direction": True, "direction": ros_yaw(degrees)}


def command_fields(event: CommandAccepted) -> dict:
    return {
        "intent": event.intent,
        "confidence": float(event.confidence),
        "by_meaning": event.by_meaning,
        "transcript": event.text,
        "slot_keys": list(event.slots.keys()),
        "slot_values": [str(value) for value in event.slots.values()],
        **_direction(event.direction_deg),
    }


def utterance_fields(event: Heard) -> dict:
    return {
        "text": event.text,
        "asr_ms": float(event.asr_ms or 0.0),
        "direction_label": event.direction or "",
        **_direction(event.direction_deg),
    }


def direction_fields(sample: DirectionSample, calibration: Calibration | None) -> dict:
    return {
        "speech": sample.energy > 0,
        "energy": float(sample.energy),
        "calibrated": calibration is not None,
        "board_degrees": float("nan") if sample.auto_beam is None else float(sample.auto_beam),
        **_direction(sample_degrees(sample, calibration)),
    }


def diagnostic(
    input_name: str | None,
    listening: bool,
    calibrated: bool,
    reconnects: int,
    failed: str | None = None,
    audio_level: str = "ok",
    audio_message: str = "Audio ok.",
    audio_rms: float = 0.0,
    audio_peak: float = 0.0,
) -> tuple[str, str, list[tuple[str, str]]]:
    """Level ("ok", "warn", "error"), message, and key/value pairs.

    audio_level is the microphone stream: ok, warn (near silence), or error
    (no frames, clipping, or the reSpeaker stalled).
    """
    values = [
        ("input", input_name or ""),
        ("listening", str(listening).lower()),
        ("direction_calibrated", str(calibrated).lower()),
        ("bridge_reconnects", str(reconnects)),
        ("audio", audio_level),
        ("audio_message", audio_message),
        ("audio_rms", f"{audio_rms:.4f}"),
        ("audio_peak", f"{audio_peak:.4f}"),
    ]
    if failed:
        return "error", failed, values
    if audio_level == "error":
        return "error", audio_message, values
    if input_name is None:
        return "warn", "Starting.", values
    if not listening:
        return "warn", "Listening paused.", values
    if audio_level == "warn":
        return "warn", audio_message, values
    return "ok", "Listening.", values
