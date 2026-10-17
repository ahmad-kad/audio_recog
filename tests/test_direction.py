"""Direction samples become a side of the rover."""

from rover_voice.audio.direction import (
    Calibration,
    DirectionSample,
    DirectionTracker,
    circular_mean,
    side_name,
)


def _sample(t: float, auto: int | None, energy: float, doa: int = 0, speech: bool = False):
    return DirectionSample(t, doa, speech, auto, auto, energy)


def test_circular_mean_wraps_around_zero():
    assert round(circular_mean([350, 10])) % 360 == 0


def test_beam_angles_without_speech_energy_are_ignored():
    tracker = DirectionTracker()
    tracker.add(_sample(1.0, 143, 0.0))  # fan between words
    tracker.add(_sample(1.1, 44, 6e6))
    tracker.add(_sample(1.2, 46, 5e5))
    assert round(tracker.board_degrees_since(0.0)) == 45


def test_doa_value_is_the_fallback():
    tracker = DirectionTracker()
    tracker.add(_sample(1.0, None, 0.0, doa=120, speech=True))
    assert round(tracker.board_degrees_since(0.0)) == 120


def test_calibration_names_sides_both_ways():
    clockwise = Calibration(front_degrees=45, clockwise=True)
    assert side_name(clockwise.to_rover(135)) == "right"
    counter = Calibration(front_degrees=45, clockwise=False)
    assert side_name(counter.to_rover(315)) == "right"
    assert side_name(counter.to_rover(225)) == "back"


def test_describe_uses_calibration():
    tracker = DirectionTracker(Calibration(front_degrees=0, clockwise=True))
    tracker.add(_sample(1.0, 270, 1e6))
    assert "left" in tracker.describe_since(0.0)


def test_degrees_need_calibration():
    tracker = DirectionTracker()
    tracker.add(_sample(1.0, 135, 5e5))
    assert tracker.degrees_since(0.0) is None
    tracker.calibration = Calibration(front_degrees=45, clockwise=True)
    assert round(tracker.degrees_since(0.0)) == 90


def test_listeners_see_every_sample():
    tracker = DirectionTracker()
    seen: list[DirectionSample] = []
    tracker.subscribe(seen.append)
    tracker.add(_sample(1.0, 10, 0.0))
    tracker.add(_sample(1.1, 20, 1.0))
    assert [s.auto_beam for s in seen] == [10, 20]
