"""Errors raised by the Mac voice prototype."""


class VoiceError(Exception):
    """Base error for capture, recognition, or local model failures."""


class AudioDeviceError(VoiceError):
    """Raised when the microphone cannot be opened."""


class ModelLoadError(VoiceError):
    """Raised when a local speech or chat model cannot be loaded."""
