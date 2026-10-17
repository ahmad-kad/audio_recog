"""The XIAO bridge parser finds frames in a raw serial byte stream."""

import struct
import threading
import time

import numpy as np
import pytest

from rover_voice.audio.serial_capture import (
    BRIDGE_FRAME_SAMPLES,
    DOA_MAGIC,
    MAGIC,
    PROTOCOL_VERSION,
    VERSION_MAGIC,
    SerialMicrophoneStream,
    is_serial_input,
    parse_stream,
)
from rover_voice.errors import AudioDeviceError


def parse_frames(buffer: bytearray):
    return parse_stream(buffer)[0]


def _frame(value: int) -> bytes:
    return MAGIC + np.full(BRIDGE_FRAME_SAMPLES, value, dtype="<i2").tobytes()


def test_frames_are_decoded_after_leading_garbage():
    buffer = bytearray(b"\x01\x02\x03" + _frame(16384) + _frame(-16384))
    frames = parse_frames(buffer)
    assert [round(float(f[0]), 3) for f in frames] == [0.5, -0.5]
    assert all(f.size == BRIDGE_FRAME_SAMPLES for f in frames)
    assert buffer == bytearray()


def test_partial_frame_waits_for_the_rest():
    data = _frame(100)
    buffer = bytearray(data[:300])
    assert parse_frames(buffer) == []
    buffer += data[300:]
    assert len(parse_frames(buffer)) == 1


def test_serial_input_names():
    assert is_serial_input("xiao")
    assert is_serial_input("/dev/cu.usbmodem101")
    assert not is_serial_input("MacBook Pro Microphone")
    assert not is_serial_input(None)


def _direction(doa: int, speech: int, free: int, auto: int, energy: float) -> bytes:
    return DOA_MAGIC + struct.pack("<HBHHf", doa, speech, free, auto, energy)


def test_direction_frames_are_split_from_audio():
    buffer = bytearray(_frame(1) + _direction(45, 1, 0xFFFF, 44, 2.5e6) + _frame(2))
    frames, directions, versions = parse_stream(buffer)
    assert versions == []
    assert len(frames) == 2
    (sample,) = directions
    assert (sample.doa, sample.speech, sample.free_beam, sample.auto_beam) == (45, True, None, 44)
    assert sample.energy == 2.5e6


class _FakePort:
    """A XIAO bridge on the other end of a serial port.

    version=None behaves like old firmware that ignores 'V'. drop_after
    raises OSError after that many audio frames, like a pulled cable.
    audio_frames stops sending audio after that many, like a stalled board.
    """

    def __init__(
        self,
        version: int | None = PROTOCOL_VERSION,
        drop_after: int | None = None,
        audio_frames: int | None = None,
    ) -> None:
        self.version = version
        self.drop_after = drop_after
        self.audio_frames = audio_frames
        self.writes: list[bytes] = []
        self.sent = 0
        self._reply = b""
        self._streaming = False
        self._lock = threading.Lock()

    def write(self, data: bytes) -> int:
        with self._lock:
            self.writes.append(bytes(data))
            if b"X" in data:
                self._streaming = False
            if b"S" in data:
                self._streaming = True
            if b"V" in data and self.version is not None:
                self._reply += VERSION_MAGIC + bytes([self.version])
        return len(data)

    def read(self, size: int) -> bytes:
        with self._lock:
            if self._reply:
                reply, self._reply = self._reply, b""
                return reply
            streaming = self._streaming
        time.sleep(0.002)
        if not streaming:
            return b""
        if self.drop_after is not None and self.sent >= self.drop_after:
            raise OSError("device disconnected")
        if self.audio_frames is not None and self.sent >= self.audio_frames:
            return b""
        self.sent += 1
        return _frame(1000)

    def reset_input_buffer(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeSerialModule:
    def __init__(self, *ports: _FakePort) -> None:
        self._ports = list(ports)

    def Serial(self, port: str, baudrate: int, timeout: float) -> _FakePort:
        if not self._ports:
            raise OSError("no device")
        return self._ports.pop(0)


def _stream(*ports: _FakePort, **options) -> SerialMicrophoneStream:
    return SerialMicrophoneStream(
        serial_module=_FakeSerialModule(*ports),
        find_port=lambda: "/dev/cu.fake",
        retry_s=0.01,
        **options,
    )


def _read_frames(stream: SerialMicrophoneStream, count: int, timeout_s: float = 3.0) -> int:
    got = 0
    deadline = time.monotonic() + timeout_s
    while got < count and time.monotonic() < deadline:
        if stream.read(timeout=0.1) is not None:
            got += 1
    return got


def test_version_frame_is_parsed():
    frames, directions, versions = parse_stream(bytearray(VERSION_MAGIC + bytes([7])))
    assert (frames, directions, versions) == ([], [], [7])


def test_matching_bridge_streams_audio():
    port = _FakePort()
    stream = _stream(port)
    stream.start("xiao")
    try:
        assert _read_frames(stream, 3) == 3
    finally:
        stream.close()
    assert b"LS" in port.writes


def test_old_firmware_without_version_is_refused():
    stream = _stream(_FakePort(version=None))
    with pytest.raises(AudioDeviceError, match="did not report a bridge protocol version"):
        stream.start("xiao")


def test_mismatched_version_is_refused():
    stream = _stream(_FakePort(version=PROTOCOL_VERSION - 1))
    with pytest.raises(AudioDeviceError, match="scripts/flash_bridge"):
        stream.start("xiao")


def test_audio_resumes_after_the_usb_link_drops():
    stream = _stream(_FakePort(drop_after=4), _FakePort())
    stream.start("xiao")
    try:
        assert _read_frames(stream, 6) == 6
    finally:
        stream.close()
    assert stream.reconnects == 1


def test_stalled_bridge_is_asked_to_stream_again():
    port = _FakePort(audio_frames=2)
    stream = _stream(port, stall_s=0.05)
    stream.start("xiao")
    try:
        time.sleep(0.4)
    finally:
        stream.close()
    assert port.writes.count(b"LS") >= 3
