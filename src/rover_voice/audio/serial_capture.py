"""reSpeaker Flex capture through the XIAO ESP32S3 USB serial bridge.

The XIAO runs firmware/xiao_mic_bridge. It streams 16 kHz mono int16 frames
(0xA5 0x5A, then 240 little-endian samples) and, about every 60 ms, a
direction frame (0xA5 0x5C, DOA u16, speech u8, free beam u16, auto beam
u16, auto beam speech energy f32). On 'V' it answers with its protocol
version (0xA5 0x5D, u8). The full protocol is in docs/respeaker.md.
"""

import logging
import queue
import struct
import threading
import time
from typing import Any, Callable

import numpy as np

from rover_voice.audio.direction import (
    Calibration,
    DirectionSample,
    DirectionTracker,
    now,
)
from rover_voice.config import FRAME_MS, SAMPLE_RATE
from rover_voice.errors import AudioDeviceError

logger = logging.getLogger(__name__)

# Must match PROTOCOL_VERSION in firmware/xiao_mic_bridge.
PROTOCOL_VERSION = 3
ESPRESSIF_VID = 0x303A
MAGIC = b"\xa5\x5a"
DOA_MAGIC = b"\xa5\x5c"
VERSION_MAGIC = b"\xa5\x5d"
BRIDGE_FRAME_SAMPLES = 240
BRIDGE_FRAME_BYTES = len(MAGIC) + BRIDGE_FRAME_SAMPLES * 2
DOA_FRAME_BYTES = len(DOA_MAGIC) + 11
VERSION_FRAME_BYTES = len(VERSION_MAGIC) + 1
_UNKNOWN_ANGLE = 0xFFFF
_SYNC = b"\xa5"
_KINDS = {
    MAGIC: BRIDGE_FRAME_BYTES,
    DOA_MAGIC: DOA_FRAME_BYTES,
    VERSION_MAGIC: VERSION_FRAME_BYTES,
}
_FLASH_HINT = "Flash the current bridge firmware with scripts/flash_bridge."


def is_serial_input(device: str | int | None) -> bool:
    return isinstance(device, str) and (
        device.lower() in {"xiao", "respeaker"} or device.startswith("/dev/")
    )


def find_xiao_port() -> str:
    from serial.tools import list_ports

    ports = [p.device for p in list_ports.comports() if p.vid == ESPRESSIF_VID]
    if not ports:
        raise AudioDeviceError(
            "No XIAO ESP32S3 found on USB. Plug a data cable into the XIAO's "
            "USB-C port, or pass the port with --input /dev/cu.usbmodemXXX."
        )
    return ports[0]


def _angle(value: int) -> int | None:
    return None if value == _UNKNOWN_ANGLE else value % 360


def parse_stream(
    buffer: bytearray,
) -> tuple[list[np.ndarray], list[DirectionSample], list[int]]:
    """Pop complete frames from buffer.

    Bytes before a known frame header are skipped. Returns audio frames as
    float32, direction samples stamped with the parse time, and any protocol
    versions the bridge reported.
    """
    frames: list[np.ndarray] = []
    directions: list[DirectionSample] = []
    versions: list[int] = []
    while True:
        start = buffer.find(_SYNC)
        if start < 0:
            buffer.clear()
            break
        if start:
            del buffer[:start]
        if len(buffer) < 2:
            break
        size = _KINDS.get(bytes(buffer[:2]))
        if size is None:
            del buffer[:1]
            continue
        if len(buffer) < size:
            break
        body = bytes(buffer[2:size])
        del buffer[:size]
        if size == BRIDGE_FRAME_BYTES:
            samples = np.frombuffer(body, dtype="<i2")
            frames.append(samples.astype(np.float32) / 32768.0)
        elif size == VERSION_FRAME_BYTES:
            versions.append(body[0])
        else:
            doa, speech, free, auto, energy = struct.unpack("<HBHHf", body)
            directions.append(
                DirectionSample(
                    time=now(),
                    doa=_angle(doa),
                    speech=bool(speech),
                    free_beam=_angle(free),
                    auto_beam=_angle(auto),
                    energy=energy,
                )
            )
    return frames, directions, versions


class SerialMicrophoneStream:
    """16 kHz mono frames and direction from the reSpeaker Flex via the XIAO.

    A background thread reads the port. If the USB link drops it reopens the
    port; if audio stops while the port stays open (the XIAO's watchdog
    rebooted it, for example) it asks the bridge to stream again.
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        frame_ms: int = FRAME_MS,
        serial_module=None,
        find_port: Callable[[], str] = find_xiao_port,
        retry_s: float = 1.0,
        stall_s: float = 2.0,
    ) -> None:
        if sample_rate != SAMPLE_RATE:
            raise AudioDeviceError("The XIAO bridge streams 16 kHz only.")
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self.directions = DirectionTracker(Calibration.load())
        self.reconnects = 0
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._serial_module = serial_module
        self._find_port = find_port
        self._retry_s = retry_s
        self._stall_s = stall_s
        self._serial: Any = None  # serial.Serial, or a fake in tests
        self._device: str | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, device: str | int | None = None) -> str:
        if self._serial_module is None:
            try:
                import serial
            except ImportError as exc:
                raise AudioDeviceError(
                    "pyserial is not available. Re-run scripts/setup.sh."
                ) from exc
            self._serial_module = serial

        self._device = device if isinstance(device, str) else None
        port = self._open_port()
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return f"reSpeaker Flex via XIAO ({port})"

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Drop audio captured while the rover was speaking."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._serial is not None:
            try:
                self._serial.write(b"X")
            except OSError:
                pass
            self._serial.close()
            self._serial = None

    def _open_port(self) -> str:
        device = self._device
        port = device if device and device.startswith("/dev/") else self._find_port()
        try:
            self._serial = self._serial_module.Serial(port, 115200, timeout=0.1)
            self._serial.write(b"X")
            time.sleep(0.15)
            self._serial.reset_input_buffer()
            version = self._ask_version()
        except OSError as exc:
            raise AudioDeviceError(f"Could not open the XIAO bridge on {port}.") from exc
        if version != PROTOCOL_VERSION:
            self._serial.close()
            if version is None:
                raise AudioDeviceError(
                    f"The XIAO on {port} did not report a bridge protocol version. "
                    + _FLASH_HINT
                )
            raise AudioDeviceError(
                f"The XIAO on {port} runs bridge protocol {version}; this app "
                f"needs {PROTOCOL_VERSION}. " + _FLASH_HINT
            )
        self._serial.write(b"LS")
        return port

    def _ask_version(self, timeout_s: float = 1.0) -> int | None:
        self._serial.write(b"V")
        raw = bytearray()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            raw += self._serial.read(64)
            versions = parse_stream(raw)[2]
            if versions:
                return versions[-1]
        return None

    def _reconnect(self) -> bool:
        """Reopen the bridge after the USB link drops. False once closed."""
        logger.warning("reSpeaker disconnected. Waiting for it to come back...")
        try:
            self._serial.close()
        except OSError:
            pass
        last_error = ""
        while self._running:
            time.sleep(self._retry_s)
            try:
                port = self._open_port()
            except AudioDeviceError as exc:
                if str(exc) != last_error:
                    last_error = str(exc)
                    logger.warning("%s", exc)
                continue
            self.reconnects += 1
            logger.warning("reSpeaker reconnected on %s.", port)
            return True
        return False

    def _read_loop(self) -> None:
        raw = bytearray()
        pending = np.zeros(0, dtype=np.float32)
        last_audio = time.monotonic()
        stalled = False
        while self._running:
            try:
                raw += self._serial.read(4096)
                if time.monotonic() - last_audio > self._stall_s:
                    if not stalled:
                        logger.warning("No audio from the reSpeaker. Asking it to stream again.")
                        stalled = True
                    self._serial.write(b"LS")
                    last_audio = time.monotonic()
            except OSError:
                if not self._running or not self._reconnect():
                    return
                raw.clear()
                pending = np.zeros(0, dtype=np.float32)
                last_audio = time.monotonic()
                continue
            frames, directions, _ = parse_stream(raw)
            for sample in directions:
                self.directions.add(sample)
            if not frames:
                continue
            if stalled:
                logger.warning("reSpeaker audio is back.")
                stalled = False
            last_audio = time.monotonic()
            pending = np.concatenate([pending, *frames])
            while pending.size >= self.frame_samples:
                self._queue.put(pending[: self.frame_samples].copy())
                pending = pending[self.frame_samples :]
