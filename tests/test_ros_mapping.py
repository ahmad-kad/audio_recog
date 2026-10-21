"""Events become ROS message fields with REP-103 angles. No ROS needed."""

import math

from rover_voice.audio.direction import Calibration, DirectionSample
from rover_voice.events import CommandAccepted, Heard
from rover_voice_ros import mapping


def test_rover_degrees_turn_into_counterclockwise_radians():
    assert mapping.ros_yaw(0.0) == 0.0
    assert math.isclose(mapping.ros_yaw(90.0), -math.pi / 2)  # right
    assert math.isclose(mapping.ros_yaw(270.0), math.pi / 2)  # left
    assert math.isclose(mapping.ros_yaw(180.0), math.pi)
    assert math.isclose(mapping.ros_yaw(315.0), math.pi / 4)  # front-left


def test_stamp_uses_speech_start_or_now():
    assert mapping.stamp(12.25, 99.0) == (12, 250_000_000)
    assert mapping.stamp(None, 99.5) == (99, 500_000_000)
    assert mapping.stamp(1.9999999999, 0.0)[1] <= 999_999_999


def test_command_fields():
    event = CommandAccepted(
        "FETCH",
        0.91,
        by_meaning=True,
        slots={"object": "hammer"},
        direction_deg=90.0,
        started_at=5.0,
        text="grab the hammer",
    )
    fields = mapping.command_fields(event)
    assert fields["intent"] == "FETCH"
    assert fields["transcript"] == "grab the hammer"
    assert fields["slot_keys"] == ["object"]
    assert fields["slot_values"] == ["hammer"]
    assert fields["has_direction"] is True
    assert math.isclose(fields["direction"], -math.pi / 2)


def test_missing_direction_is_flagged_not_zero():
    fields = mapping.utterance_fields(Heard("hello", asr_ms=None))
    assert fields == {
        "text": "hello",
        "asr_ms": 0.0,
        "direction_label": "",
        "has_direction": False,
        "direction": 0.0,
    }


def test_direction_sample_needs_speech_and_calibration():
    calibration = Calibration(front_degrees=0.0, clockwise=True)
    quiet = DirectionSample(1.0, 0, False, 0, 143, 0.0)
    loud = DirectionSample(1.0, 0, True, 0, 270, 4e5)
    assert mapping.direction_fields(quiet, calibration)["has_direction"] is False
    fields = mapping.direction_fields(loud, calibration)
    assert fields["speech"] is True
    assert math.isclose(fields["direction"], math.pi / 2)
    uncalibrated = mapping.direction_fields(loud, None)
    assert uncalibrated["calibrated"] is False
    assert uncalibrated["has_direction"] is False
    assert uncalibrated["board_degrees"] == 270.0
    unknown = DirectionSample(1.0, None, False, None, None, 0.0)
    assert math.isnan(mapping.direction_fields(unknown, None)["board_degrees"])


def test_diagnostic_levels():
    assert mapping.diagnostic(None, True, False, 0)[0] == "warn"
    assert mapping.diagnostic("xiao", True, True, 2)[0] == "ok"
    assert mapping.diagnostic("xiao", False, True, 0)[1] == "Listening paused."
    level, message, values = mapping.diagnostic("xiao", True, True, 0, "no mic")
    assert (level, message) == ("error", "no mic")
    assert ("bridge_reconnects", "0") in values
    level, message, values = mapping.diagnostic(
        "xiao",
        True,
        True,
        0,
        audio_level="error",
        audio_message="Audio is clipping.",
        audio_rms=0.2,
        audio_peak=1.0,
    )
    assert (level, message) == ("error", "Audio is clipping.")
    assert ("audio", "error") in values
    assert ("audio_peak", "1.0000") in values
    level, message, _ = mapping.diagnostic(
        "xiao", True, True, 0, audio_level="warn", audio_message="Audio level is near silence."
    )
    assert (level, message) == ("warn", "Audio level is near silence.")
